#author : Pierre Ratinaud
#copyright 1012 Pierre Ratinaud
#license : GNU GPL


in.table <- read.csv2('/home/pierre/workspace/iramuteq/corpus/association_suede.csv', header = FALSE, row.names=1)
source('/home/pierre/workspace/iramuteq/Rscripts/Rgraph.R')

verges.table <- function(x, freq.ts = 'mean', rank.ts = 'mean') {
#x matrice : eff, rank
#table.out : eff in rows, rank in columns
#            1|2
#            3|4
    if (freq.ts == 'mean') {
        freq.ts <- mean(x[,1])
    }
    if (rank.ts == 'mean') {
        rank.ts <- mean(x[,2])
    }

    eff.cex=c(0.8,2)
    rank.cex=NULL

    if (!is.null(eff.cex)) x <- cbind(x,norm.eff=norm.vec(x[,1],eff.cex[1], eff.cex[2]))
    
    if (!is.null(rank.cex)) x <- cbind(x,norm.rank=norm.vec(x[,1],rank.cex[1], rank.cex[2]))

    case.1 <- x[which(x[,1] >= freq.ts & x[,2] <= rank.ts),]
    case.2 <- x[which(x[,1] >= freq.ts & x[,2] > rank.ts),]
    case.3 <- x[which(x[,1] < freq.ts & x[,2] <= rank.ts),]
    case.4 <- x[which(x[,1] < freq.ts & x[,2] > rank.ts),]

    ylims <- max(c(nrow(case.1), nrow(case.2), nrow(case.3) ,nrow(case.4)))
    

    plot.case <- function(case) {
        txt <- rownames(case)
        if (ncol(case) == 3) lab.cex <- case[,3]
        else lab.cex=1
        plot(rep(1,length(txt)),1:length(txt),pch='',axes=FALSE, xlab='', ylab='', ylim = c(0,ylims))
        ys <- ylims - length(txt)
        ys <- (length(txt):1) + ys
        text(1,ys,txt, xlab=NULL, ylab=NULL, cex=lab.cex)
    }

    boxcolor = 'green'
    par(mfcol=c(2,2))
    par(mar=c(1,1,1,1))
    par(oma=c(3,3,3,3))
    plot.case(case.1)
    box("figure", col=boxcolor)
    plot.case(case.3)
    box("figure", col=boxcolor)
    plot.case(case.2)
    box("figure", col=boxcolor)
    plot.case(case.4)
    box("figure", col=boxcolor)

    mtext("rangs <= | rangs >", side=3, line=1, cex=1, col="blue", outer=TRUE)   
    mtext("fréquences < | fréquences >=", side=2, line=2, cex=1, col="blue", outer=TRUE)  
    box("outer", col="blue") 
}


    
