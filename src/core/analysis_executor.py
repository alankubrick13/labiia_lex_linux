"""
Analysis Executor Module for LabiiaLex.

This module manages the execution of text analyses, including
task queuing, progress reporting, and result handling.
"""

from __future__ import annotations

import logging
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Any, Callable, List
from queue import Queue

from .corpus import Corpus
from .text_processor import TextProcessor
from .r_script_generator import RScriptGenerator
from .r_executor import RExecutor

log = logging.getLogger(__name__)


class AnalysisType(Enum):
    """Supported analysis types."""
    CHD = "chd"
    SIMILARITY = "similarity"
    WORDCLOUD = "wordcloud"


class TaskStatus(Enum):
    """Analysis task status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AnalysisTask:
    """
    Represents an analysis task.
    
    Attributes:
        task_id: Unique identifier
        analysis_type: Type of analysis (CHD, similarity, etc.)
        parameters: Analysis parameters dictionary
        status: Current task status
        progress: Progress percentage (0-100)
        result_path: Path to results directory
        error: Error message if failed
        created_at: Creation timestamp
        started_at: Start timestamp
        completed_at: Completion timestamp
    """
    task_id: str
    analysis_type: AnalysisType
    parameters: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    result_path: Optional[Path] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @classmethod
    def create(cls, analysis_type: AnalysisType | str, 
               parameters: Dict[str, Any]) -> 'AnalysisTask':
        """Create a new analysis task."""
        if isinstance(analysis_type, str):
            analysis_type = AnalysisType(analysis_type.lower())
        
        return cls(
            task_id=str(uuid.uuid4()),
            analysis_type=analysis_type,
            parameters=parameters
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            'task_id': self.task_id,
            'analysis_type': self.analysis_type.value,
            'status': self.status.value,
            'progress': self.progress,
            'result_path': str(self.result_path) if self.result_path else None,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class AnalysisExecutorError(Exception):
    """
    Exception for analysis execution errors.
    
    Provides user-friendly error messages following the What/Why/How pattern.
    """
    
    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        super().__init__(f"{what}\n\nMotivo: {why}\n\nSolução: {how}")


class AnalysisExecutor:
    """
    Manages execution of text analyses.
    
    Coordinates between TextProcessor, RScriptGenerator, and RExecutor
    to prepare data, generate scripts, and run analyses.
    
    Attributes:
        corpus: The Corpus to analyze
        output_dir: Base directory for output files
        r_executor: RExecutor instance for running R scripts
    """
    
    def __init__(self, corpus: Corpus, output_dir: Path,
                 r_executor: Optional[RExecutor] = None):
        """
        Initialize AnalysisExecutor.
        
        Args:
            corpus: Corpus object to analyze
            output_dir: Base directory for analysis outputs
            r_executor: Optional RExecutor (creates one if not provided)
        """
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.r_executor = r_executor or RExecutor()
        self.script_generator = RScriptGenerator()
        self.text_processor = TextProcessor(corpus)
        
        self._tasks: Dict[str, AnalysisTask] = {}
        self._queue: Queue = Queue()
        self._progress_callback: Optional[Callable[[str, int, str], None]] = None
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    # -------------------------------------------------------------------------
    # Task Management
    # -------------------------------------------------------------------------
    
    def queue_analysis(self, analysis_type: AnalysisType | str,
                       parameters: Optional[Dict[str, Any]] = None) -> AnalysisTask:
        """
        Queue an analysis for execution.
        
        Args:
            analysis_type: Type of analysis
            parameters: Analysis parameters (optional)
            
        Returns:
            Created AnalysisTask
        """
        params = parameters or {}
        task = AnalysisTask.create(analysis_type, params)
        
        with self._lock:
            self._tasks[task.task_id] = task
        
        self._queue.put(task.task_id)
        log.info(f"Queued analysis: {task.task_id} ({task.analysis_type.value})")
        
        return task
    
    def get_status(self, task_id: str) -> Optional[AnalysisTask]:
        """Get current status of a task."""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> List[AnalysisTask]:
        """Get all tasks."""
        with self._lock:
            return list(self._tasks.values())
    
    def cancel_analysis(self, task_id: str) -> bool:
        """
        Cancel a pending or running analysis.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if cancelled, False if not found or not cancellable
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                log.info(f"Cancelled analysis: {task_id}")
                return True
        
        return False
    
    def set_progress_callback(self, 
                              callback: Callable[[str, int, str], None]) -> None:
        """
        Set callback for progress updates.
        
        Callback receives (task_id, progress_percentage, status_message).
        
        Args:
            callback: Function to call on progress updates
        """
        self._progress_callback = callback
    
    def _update_progress(self, task_id: str, progress: int, 
                         message: str = "") -> None:
        """Update task progress and notify callback."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.progress = progress
        
        if self._progress_callback:
            try:
                self._progress_callback(task_id, progress, message)
            except Exception as e:
                log.warning(f"Progress callback error: {e}")
    
    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------
    
    def run_analysis(self, task: AnalysisTask) -> AnalysisTask:
        """
        Execute a single analysis synchronously.
        
        Args:
            task: AnalysisTask to execute
            
        Returns:
            Updated AnalysisTask with results
        """
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        try:
            self._update_progress(task.task_id, 0, "Iniciando análise...")
            
            # Create output directory for this analysis
            task_dir = self.output_dir / task.task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            task.parameters['pathout'] = str(task_dir)
            
            # Execute based on analysis type
            if task.analysis_type == AnalysisType.CHD:
                self._run_chd(task, task_dir)
            elif task.analysis_type == AnalysisType.SIMILARITY:
                self._run_similarity(task, task_dir)
            elif task.analysis_type == AnalysisType.WORDCLOUD:
                self._run_wordcloud(task, task_dir)
            else:
                raise AnalysisExecutorError(
                    what=f"Tipo de análise não suportado: {task.analysis_type}",
                    why="O executor não reconhece este tipo de análise.",
                    how="Use um dos tipos suportados: CHD, SIMILARITY, WORDCLOUD."
                )
            
            task.status = TaskStatus.COMPLETED
            task.result_path = task_dir
            task.progress = 100
            self._update_progress(task.task_id, 100, "Análise concluída!")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            log.error(f"Analysis failed: {task.task_id} - {e}")
            self._update_progress(task.task_id, -1, f"Erro: {e}")
        
        task.completed_at = datetime.now()
        return task
    
    def _run_chd(self, task: AnalysisTask, task_dir: Path) -> None:
        """Execute CHD analysis."""
        self._update_progress(task.task_id, 10, "Exportando dados...")
        
        # Build DTM and export
        min_freq = task.parameters.get('min_freq', 3)
        self.text_processor.build_dtm(min_freq=min_freq)
        files = self.text_processor.export_for_chd(task_dir)
        
        self._update_progress(task.task_id, 30, "Gerando script R...")

        typegraph = str(task.parameters.get('typegraph', 'png')).lower()
        if typegraph not in {'png', 'svg'}:
            typegraph = 'png'
        graph_out = 'dendrogramme.svg' if typegraph == 'svg' else 'dendrogramme.png'
        
        # Generate R script
        params = {
            **task.parameters,
            'pathout': str(task_dir),
            'typegraph': typegraph,
            'data_file': files['dtm'].name,
            'graph_out': graph_out,
        }
        script_path = self.script_generator.generate_and_save('chd', params, 
                                                               task_dir / 'chd_script.R')
        
        self._update_progress(task.task_id, 50, "Executando análise R...")
        
        # Run R script
        self._execute_r_script(script_path, task_dir)
        
        self._update_progress(task.task_id, 90, "Finalizando...")
    
    def _run_similarity(self, task: AnalysisTask, task_dir: Path) -> None:
        """Execute similarity analysis."""
        self._update_progress(task.task_id, 10, "Exportando dados...")
        
        min_freq = task.parameters.get('min_freq', 3)
        window_size = task.parameters.get('window_size', 5)
        self.text_processor.build_dtm(min_freq=min_freq)
        self.text_processor.build_cooccurrence_matrix(window_size=window_size)
        files = self.text_processor.export_for_similarity(task_dir)
        
        self._update_progress(task.task_id, 30, "Gerando script R...")

        typegraph = str(task.parameters.get('typegraph', 'png')).lower()
        if typegraph not in {'png', 'svg'}:
            typegraph = 'png'
        graph_out = 'similarity.svg' if typegraph == 'svg' else 'similarity.png'
        
        params = {
            **task.parameters,
            'pathout': str(task_dir),
            'data_file': files['cooccurrence'].name,
            'typegraph': typegraph,
            'graph_out': graph_out,
        }
        script_path = self.script_generator.generate_and_save('similarity', params,
                                                               task_dir / 'similarity_script.R')
        
        self._update_progress(task.task_id, 50, "Executando análise R...")
        
        self._execute_r_script(script_path, task_dir)
        
        self._update_progress(task.task_id, 90, "Finalizando...")
    
    def _run_wordcloud(self, task: AnalysisTask, task_dir: Path) -> None:
        """Execute word cloud generation."""
        self._update_progress(task.task_id, 10, "Preparando dados...")
        
        # Export word frequencies
        freq_file = task_dir / 'words.csv'
        freqs = self.text_processor.get_word_frequencies(
            use_lemmas=bool(task.parameters.get("use_lemmas", True)),
            active_only=bool(task.parameters.get("active_only", True)),
        )
        
        with open(freq_file, 'w', encoding='utf-8') as f:
            f.write("word;freq\n")
            for word, freq in freqs:
                f.write(f"{word};{freq}\n")
        
        self._update_progress(task.task_id, 30, "Gerando script R...")

        typegraph = str(task.parameters.get('typegraph', 'png')).lower()
        if typegraph not in {'png', 'svg'}:
            typegraph = 'png'
        graph_out = 'wordcloud.svg' if typegraph == 'svg' else 'wordcloud.png'
        
        params = {
            **task.parameters,
            'pathout': str(task_dir),
            'typegraph': typegraph,
            'data_file': 'words.csv',
            'graph_out': graph_out,
        }
        script_path = self.script_generator.generate_and_save('wordcloud', params,
                                                               task_dir / 'wordcloud_script.R')
        
        self._update_progress(task.task_id, 50, "Executando análise R...")
        
        self._execute_r_script(script_path, task_dir)
        
        self._update_progress(task.task_id, 90, "Finalizando...")
    
    def _execute_r_script(self, script_path: Path, work_dir: Path) -> None:
        """Execute R script using RExecutor."""
        from .r_executor import RNotFoundError, RExecutionError, RTimeoutError
        
        if not self.r_executor.r_path:
            raise AnalysisExecutorError(
                what="R não encontrado no sistema.",
                why="O executor R não conseguiu localizar uma instalação do R.",
                how="Instale o R (versão 4.0+) e verifique se está no PATH."
            )
        
        try:
            result = self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(work_dir),
                timeout=300  # 5 minute timeout
            )
            log.info(f"R script executed successfully: {script_path}")
        except RNotFoundError as e:
            raise AnalysisExecutorError(
                what="R não encontrado no sistema.",
                why=str(e),
                how="Instale o R (versão 4.0+) e verifique se está no PATH."
            ) from e
        except RTimeoutError as e:
            raise AnalysisExecutorError(
                what="Tempo limite excedido na execução do script R.",
                why=str(e),
                how="Reduza o tamanho do corpus ou aumente o tempo limite."
            ) from e
        except RExecutionError as e:
            raise AnalysisExecutorError(
                what="Falha na execução do script R.",
                why=str(e),
                how="Verifique se todas as bibliotecas R necessárias estão instaladas."
            ) from e
    
    # -------------------------------------------------------------------------
    # Background Processing
    # -------------------------------------------------------------------------
    
    def start_worker(self) -> None:
        """Start background worker thread for processing queued analyses."""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        log.info("Analysis worker started")
    
    def stop_worker(self) -> None:
        """Stop background worker thread."""
        self._running = False
        self._queue.put(None)  # Signal to stop
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        log.info("Analysis worker stopped")
    
    def _worker_loop(self) -> None:
        """Main loop for background worker."""
        while self._running:
            try:
                task_id = self._queue.get(timeout=1.0)
                if task_id is None:
                    break
                
                with self._lock:
                    task = self._tasks.get(task_id)
                
                if task and task.status == TaskStatus.PENDING:
                    self.run_analysis(task)
                
            except Exception as e:
                if self._running:
                    log.error(f"Worker error: {e}")
    
    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------
    
    def run_chd(self, **kwargs) -> AnalysisTask:
        """Convenience method to run CHD analysis."""
        task = self.queue_analysis(AnalysisType.CHD, kwargs)
        return self.run_analysis(task)
    
    def run_similarity(self, **kwargs) -> AnalysisTask:
        """Convenience method to run similarity analysis."""
        task = self.queue_analysis(AnalysisType.SIMILARITY, kwargs)
        return self.run_analysis(task)
    
    def run_wordcloud(self, **kwargs) -> AnalysisTask:
        """Convenience method to run word cloud generation."""
        task = self.queue_analysis(AnalysisType.WORDCLOUD, kwargs)
        return self.run_analysis(task)
