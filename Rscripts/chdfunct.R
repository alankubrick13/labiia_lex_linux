#datadm<-read.table('/home/pierre/.hippasos/corpus_agir_CHDS_16/fileACTtemp.csv', header=TRUE,sep=';', quote='\"',row.names = 1, na.strings = 'NA')
library(cluster)
#dissmat<-daisy(dataact, metric = 'gower', stand = FALSE)
#chd<-diana(dissmat,diss=TRUE,)
#height<-chd$height
#sortheight<-sort(height,decreasing=TRUE)
FindBestCluster<-function (x,Max=15) {
    i<-1
    j<-1
    ListClasseOk<-list()
    while (i < Max) {
        if (x[i]==1){
            while (x[i]==1) {
            i<-i+1
            }
            ListClasseOk[[j]]<-i
            j<-j+1
        }
        if (x[i]==x[i+1]) {
            i<-i+1
        }
        else {
            ListClasseOk[[j]]<-i+1
            i<-i+1
            j<-j+1
        }
    }
        unlist(ListClasseOk)
}
#BestCLusterNb<-FindBestCluster(sortheight)
#classes<-as.data.frame(cutree(as.hclust(chd), k=6))[,1]
#datadm<-cbind(datadm,classes)
#clusplot(datadm,classes,shade=TRUE,color=TRUE,labels=4)

BuildContTable<- function (x) {
        afctable<-NULL
        for (i in 1:(ncol(x)-1)) {
            coltable<-table(x[,i],x$classes)
            afctable<-rbind(afctable,coltable)
        }
        afctable
}

PrintProfile<- function(dataclasse,profileactlist,profileetlist,antiproact,antiproet,clusternb,profileout,antiproout,profilesuplist=NULL,antiprosup=NULL) {
    prolist<-list()
    profile<-matrix(,0,6)
    antipro<-matrix(,0,6)
	cltot<-as.data.frame(dataclasse[dataclasse[,ncol(dataclasse)]!=0,])
	cltot<-as.data.frame(as.character(cltot[,ncol(cltot)]))
	tot<-nrow(cltot)
    classes<-as.data.frame(as.character(dataclasse[,ncol(dataclasse)]))
    classes.s<-as.data.frame(summary(as.factor(cltot[,1]),maxsum=500))
    profile<-rbind(profile,c('***','nb classes',clusternb,'***','',''))
    antipro<-rbind(antipro,c('***','nb classes',clusternb,'***','',''))
    for(i in 1:clusternb) {
        profile<-rbind(profile,c('**','classe',i,'**','',''))
        nbind<-classes.s[which(rownames(classes.s)==i),1]
        pr<-round((nbind/tot)*100,digits=2)
        profile<-rbind(profile,c('****',nbind,tot,pr,'****',''))
		if (length(profileactlist[[1]][[i]])!=0){
        	profile<-rbind(profile,as.matrix(profileactlist[[1]][[i]]))
		}
		if (!is.null(profilesuplist)) {
			profile<-rbind(profile,c('*****','*','*','*','*','*'))
			if (length(profilesuplist[[1]][[i]])!=0) {
				profile<-rbind(profile,as.matrix(profilesuplist[[1]][[i]]))
			}		
		}
        if (!is.null(profileetlist)) {
            profile<-rbind(profile,c('*','*','*','*','*','*'))
		    if (length(profileetlist[[1]][[i]])!=0) {
        	    profile<-rbind(profile,as.matrix(profileetlist[[1]][[i]]))
		    }
        }
        antipro<-rbind(antipro,c('**','classe',i,'**','',''))
        antipro<-rbind(antipro,c('****',nbind,tot,pr,'****',''))
		if (length(antiproact[[1]][[i]])!=0) {
        	antipro<-rbind(antipro,as.matrix(antiproact[[1]][[i]]))
		}
		if (!is.null(profilesuplist)) {
			antipro<-rbind(antipro,c('*****','*','*','*','*','*'))
			if (length(antiprosup[[1]][[i]])!=0) {
				antipro<-rbind(antipro,as.matrix(antiprosup[[1]][[i]]))
			}
		}
        if (!is.null(profileetlist)) {
            antipro<-rbind(antipro,c('*','*','*','*','*','*'))
            if (length(antiproet[[1]][[i]])!=0) {
			    antipro<-rbind(antipro,as.matrix(antiproet[[1]][[i]]))
		    }
        }
	}
    write.csv2(profile,file=profileout,row.names=FALSE)
    write.csv2(antipro,file=antiproout,row.names=FALSE)
}

AddCorrelationOk<-function(afc) {
	rowcoord<-afc$rowcoord
	colcoord<-afc$colcoord
	factor <- ncol(rowcoord)
	
	hypo<-function(rowcoord,ligne) {
		somme<-0
		for (i in 1:factor) {
			somme<-somme+(rowcoord[ligne,i])^2
		}
		sqrt(somme)
	}
	cor<-function(d,hypo) {
		d/hypo
	}
	CompCrl<-function(rowcol) {
		out<-rowcol
		for (i in 1:factor) {
			for(ligne in 1:nrow(rowcol)) {      
				out[ligne,i]<-cor(rowcol[ligne,i],hypo(rowcol,ligne))
			}
		}
	out
	}

	get.corr <- function(rowcol) {
		sqrowcol <- rowcol^2
		sqrowcol <- sqrt(rowSums(sqrowcol))
		corr <- rowcol / sqrowcol
		corr
	}
	#afc$rowcrl<-CompCrl(rowcoord)
	afc$rowcrl <- get.corr(rowcoord)
	#afc$colcrl<-CompCrl(colcoord)
	afc$colcrl<-get.corr(colcoord)
	afc
}

AsLexico<- function(x) {
	x<-as.matrix(x)
	sumcol<-colSums(x)
    sumrow<-rowSums(x)
	tot<-sum(sumrow)
	tablesqr<-x
	tablep<-x
	mod.names<-rownames(x)
	#problem exemple aurelia
	for (classe in 1:ncol(x)) {
		print(classe)
		for (ligne in 1:nrow(x)) {
			conttable<-matrix(0,2,2)
			conttable[1,1]<-as.numeric(x[ligne,classe])
			conttable[1,2]<-sumrow[ligne]-conttable[1,1]
			conttable[2,1]<-sumcol[classe]-conttable[1,1]
			conttable[2,2]<-tot-sumrow[ligne]-conttable[2,1]
			chiresult<-chisq.test(conttable,correct=TRUE)
			if (is.na(chiresult$p.value)) {
				chiresult$p.value<-1
				chiresult$statistic<-0
			}
			obsv<-chiresult$expected
			pval<-as.character(format(chiresult$p.value,scientific=TRUE))
			spval<-strsplit(pval,'e')
			if (is.na(spval)) {
				print(spval)
			}
			if (conttable[1,1]>obsv[1,1]) {
				tablep[ligne,classe]<-as.numeric(spval[[1]][2])*(-1)
				tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
			}
			else if (conttable[1,1]<obsv[1,1]){
				tablep[ligne,classe]<-as.numeric(spval[[1]][2])
				tablesqr[ligne,classe]<--round(chiresult$statistic,digits=3)
			}
		}
	}
	output<-list()
	eff_relatif<-(x/sumcol)*1000
	output[[1]]<-tablep
	output[[2]]<-tablesqr
	output[[3]]<-eff_relatif
	output
}		

MyChiSq<-function(x){
	sr<-rowSums(x)
    sc<-colSums(x)
    n <- sum(x)
	E <- outer(sr, sc, "*")/n
	STAT<-sum((abs(x - E))^2/E)
    PVAL <- pchisq(STAT, 1, lower.tail = FALSE)
	chi<-list(statistic = STAT, expected = E, p.value = PVAL)
    chi
}

AsLexico2<- function(mat, chip = FALSE) {
	mat<-as.matrix(mat)
	sumcol<-colSums(mat)
	sumrow<-rowSums(mat)
	tot<-sum(sumrow)
	tablesqr<-mat
	tablep<-mat
    contcs <- mat
    for (i in 1:nrow(contcs)) {
        contcs[i,] <- sumcol
    }
    contrs <- mat
    contrs[,1:ncol(contrs)] <- sumrow
    conttot <- matrix(tot, nrow = nrow(mat), ncol = ncol(mat))
    cont12 <- contrs - mat
    cont21 <- contcs - mat
    cont22 <- conttot - contrs - cont21
	mod.names<-rownames(mat)
    make_chi_lex <- function(x) {
        tb<-matrix(0,2,2)
        tb[1,1] <- mat[x]
        tb[1,2] <- cont12[x]
        tb[2,1] <- cont21[x]
        tb[2,2] <- cont22[x]
        chiresult<-MyChiSq(tb)
        #chiresult$statistic
        if (is.na(chiresult$p.value)) {
			chiresult$p.value<-1
			chiresult$statistic<-0
		}
		obsv<-chiresult$expected
		pval<-as.character(format(chiresult$p.value,scientific=TRUE))
		spval<-strsplit(pval,'e')
		if (is.na(spval)) {
			print(spval)
		}
		if (tb[1,1]>obsv[1,1]) {
			as.numeric(spval[[1]][2])*(-1)
		}
		else if (tb[1,1]<obsv[1,1]){
			as.numeric(spval[[1]][2])
		} else {
            0
        }
    }
    make_chi_p <- function(x) {
        tb<-matrix(0,2,2)
        tb[1,1] <- mat[x]
        tb[1,2] <- cont12[x]
        tb[2,1] <- cont21[x]
        tb[2,2] <- cont22[x]
        chiresult<-MyChiSq(tb)
        #chiresult$statistic
        if (is.na(chiresult$p.value)) {
			chiresult$p.value<-1
			chiresult$statistic<-0
		}
		obsv<-chiresult$expected
		if (tb[1,1]>obsv[1,1]) {
			chiresult$p.value
		}
		else if (tb[1,1]<obsv[1,1]){
			1
		} else {
            1
        }
    }
    make_chi <- function(x) {
        tb<-matrix(0,2,2)
        tb[1,1] <- mat[x]
        tb[1,2] <- cont12[x]
        tb[2,1] <- cont21[x]
        tb[2,2] <- cont22[x]
        chiresult<-MyChiSq(tb)
        #chiresult$statistic
        if (is.na(chiresult$p.value)) {
			chiresult$p.value<-1
			chiresult$statistic<-0
		}
		obsv<-chiresult$expected
		if (tb[1,1]>obsv[1,1]) {
			chiresult$statistic
		}
		else if (tb[1,1]<obsv[1,1]){
			0
		} else {
            0
        }
    }

    res <- matrix(sapply(1:length(mat), make_chi_lex), ncol = ncol(mat))
    rownames(res)<-mod.names
    colnames(res) <- colnames(mat)
    eff_relatif<-round(t(apply(mat,1,function(x) {(x/t(as.matrix(sumcol))*1000)})),2)
    rownames(eff_relatif)<-mod.names
    colnames(eff_relatif) <- colnames(mat)
    if (chip) {
        reschip <- matrix(sapply(1:length(mat), make_chi_p), ncol = ncol(mat))
        rownames(reschip)<- mod.names
        colnames(reschip) <- colnames(mat)
        reschi <- matrix(sapply(1:length(mat), make_chi), ncol = ncol(mat))
        rownames(reschip)<- mod.names
        colnames(reschip) <- colnames(mat)
    }
    out <-list()
    out[[1]]<-res
    out[[3]]<-eff_relatif
    if (chip) {
        out[[2]] <- reschip
        out[[4]] <- reschi
    }
    out
}

make.spec.hypergeo <- function(mat) {
    library(textometry)
    spec <- specificities(mat)
	sumcol<-colSums(mat)
    eff_relatif<-round(t(apply(mat,1,function(x) {(x/t(as.matrix(sumcol))*1000)})),2)
    colnames(eff_relatif) <- colnames(mat)
    out <-list()
    out[[1]]<-spec
    out[[3]]<-eff_relatif
    out
}

make.spec.chrono.bef <- function(mat, empan = 1) {
        library(textometry)
        spec <- NULL
        for (dat in (empan+1):ncol(mat)) {
                nmat <- cbind(rowSums(mat[,(dat-empan):dat]), mat[,(dat)])
                spec.dat  <- specificities(nmat)
                spec <- cbind(spec,spec.dat[,2])
                #colnames(spec)[-1] <- colnames(mat)[dat]
        }
        for (val in 1:empan) {
                spec <- cbind(rep(0,nrow(mat)), spec)
        }
        colnames(spec) <- colnames(mat)
        sumcol<-colSums(mat)
    eff_relatif<-round(t(apply(mat,1,function(x) {(x/t(as.matrix(sumcol))*1000)})),2)
    colnames(eff_relatif) <- colnames(mat)
    out <-list()
    out[[1]]<-spec
    out[[3]]<-eff_relatif
    out
}

BuildProf01<-function(x,classes) {
	#x : donnees en 0/1
	#classes : classes de chaque lignes de x
	dm<-cbind(x,cl=classes)
	clnb=length(summary(as.data.frame(as.character(classes)),max=100))
	mat<-matrix(0,ncol(x),clnb)
	rownames(mat)<-colnames(x)
	for (i in 1:clnb) {
		dtmp<-dm[which(dm$cl==i),]
		for (j in 1:(ncol(dtmp)-1)) {
			mat[j,i]<-sum(dtmp[,j])
		}
	}
	mat
}

build.prof.tgen <- function(x) {
    nbst <- sum(x[nrow(x),])
    totcl <- x[nrow(x),]
    tottgen <- rowSums(x)
    nbtgen <- nrow(x) - 1
    chi2 <- x[1:(nrow(x)-1),]
    pchi2 <- chi2
    for (classe in 1:ncol(x)) {
        for (tg in 1:nbtgen) {
            cont <- c(x[tg, classe], tottgen[tg] - x[tg, classe], totcl[classe] - x[tg, classe], (nbst - totcl[classe]) - (tottgen[tg] - x[tg, classe]))
            cont <- matrix(unlist(cont), nrow=2)
            chiresult<-chisq.test(cont,correct=FALSE)
            if (is.na(chiresult$p.value)) {
                chiresult$p.value<-1
                chiresult$statistic<-0
            }
            if (chiresult$expected[1,1] > cont[1,1]) {
                chiresult$statistic <- chiresult$statistic * -1
            }
            chi2[tg,classe] <- chiresult$statistic
            pchi2[tg,classe] <- chiresult$p.value
        }
    }
    res <- list(chi2 = chi2, pchi2 = pchi2)
}


new.build.prof <- function(x,dataclasse,clusternb,lim=2) {
	cl <- dataclasse[,ncol(dataclasse)]
	nst <- length(which(cl != 0))
	rs <- rowSums(x)
	mod.names<-rownames(x)
	lnbligne <- list()
	lchi <- list()
	prof <- list()
	aprof <- list()
	for (classe in 1:clusternb) {
		lnbligne[[classe]]<-length(which(cl==classe))
		tmpprof <- data.frame()
		tmpanti <- data.frame()
		obs1 <- x[,classe] #1,1
		obs2 <- rs - obs1 #1,2
	    obs3 <- lnbligne[[classe]] - obs1	#2,1
		obs4 <- nst - (obs1 + obs2 + obs3) #2,2
		exp1 <- ((obs1 + obs3) * (obs1 + obs2)) / nst
		exp2 <- ((obs2 + obs1) * (obs2 + obs4)) / nst
		exp3 <- ((obs3 + obs4) * (obs3 + obs1)) / nst
		exp4 <- ((obs4 + obs3) * (obs4 + obs2)) / nst
		chi1 <- ((obs1 - exp1)^2) / exp1
		chi2 <- ((obs2 - exp2)^2) / exp2
		chi3 <- ((obs3 - exp3)^2) / exp3
		chi4 <- ((obs4 - exp4)^2) / exp4
		chi <- chi1 + chi2 + chi3 + chi4	
		chi[which(is.na(chi)==T)] <- 0
		tochange <- ifelse(obs1 > exp1, 1, -1)
		lchi[[classe]] <- chi * tochange
		tokeep <- which(lchi[[classe]] > lim)
		if (length(tokeep)) {
			tmpprof[1:length(tokeep),1] <- obs1[tokeep]
			tmpprof[,2] <- rs[tokeep]
			tmpprof[,3] <- round((obs1/rs)*100, digits=2)[tokeep]
			tmpprof[,4] <- round(lchi[[classe]], digits=3)[tokeep]
			tmpprof[,5] <- mod.names[tokeep] 
			tmpprof[,6] <- pchisq(lchi[[classe]] ,1, lower.tail=F)[tokeep]
		}
		prof[[classe]] <- tmpprof
		toanti <- which(lchi[[classe]] < -lim)
		if (length(toanti)) {
			tmpanti[1:length(toanti),1] <- obs1[toanti]
			tmpanti[,2] <- rs[toanti]
			tmpanti[,3] <- round((obs1/rs)*100, digits=2)[toanti]
			tmpanti[,4] <- round(lchi[[classe]], digits=3)[toanti]
			tmpanti[,5] <- mod.names[toanti] 
			tmpanti[,6] <- pchisq(-lchi[[classe]] ,1, lower.tail=F)[toanti]
		}
		aprof[[classe]] <- tmpanti
		if (length(prof[[classe]])!=0) {
			prof[[classe]]<-prof[[classe]][order(prof[[classe]][,4],decreasing=TRUE),]
		}
		if (length(aprof[[classe]])!=0) {
			aprof[[classe]]<-aprof[[classe]][order(aprof[[classe]][,4]),]	
		}
	}
    tablechi <- do.call(cbind, lchi)
	tablep <- pchisq(tablechi,1, lower.tail=F)
	tablep <- round(tablep, digits=3)
	tablechi <- round(tablechi, digits=3)
	out <- list()
	out[[1]] <- tablep
	out[[2]] <- tablechi
	out[[3]] <- cbind(x, rowSums(x))
    out[[4]] <- prof	
	out[[5]] <- aprof
	out
}


BuildProf<- function(x,dataclasse,clusternb,lim=2) {
	print('build prof')
	####
	#r.names<-rownames(x)
	#x<-as.matrix(x)
	#rownames(x)<-r.names
	####
	#nuce<-nrow(dataclasse)
    sumcol<-paste(NULL,1:nrow(x))
	colclasse<-dataclasse[,ncol(dataclasse)]
	nuce <- length(which(colclasse != 0))
#	for (i in 1:nrow(x)) {
#		sumcol[i]<-sum(x[i,])
#	}
#	afctablesum<-cbind(x,sumcol)
    afctablesum <- cbind(x, rowSums(x))
    #dataclasse<-as.data.frame(dataclasse[dataclasse[,ncol(dataclasse)]!=0,])
	dataclasse<-as.matrix(dataclasse[dataclasse[,ncol(dataclasse)]!=0,])
	tablesqr<-x
	tablep<-x
	x<-afctablesum
	listprofile<-list()
	listantipro<-list()
	mod.names<-rownames(x)
	prof<-list()
	aprof<-list()
	lnbligne<-matrix()
	for (classe in 1:clusternb) {
		lnbligne[classe]<-length(colclasse[colclasse==classe])
		prof[[classe]]<-data.frame()
		aprof[[classe]]<-data.frame()
	}
	
	for (ligne in 1:nrow(x)) {
		for (classe in 1:clusternb) {
			nbligneclasse<-lnbligne[classe]
			conttable<-data.frame()
			conttable[1,1]<-as.numeric(x[ligne,classe])
			conttable[1,2]<-as.numeric(as.vector(x[ligne,ncol(x)]))-as.numeric(x[ligne,classe])
			conttable[2,1]<-nbligneclasse-as.numeric(x[ligne,classe])
			conttable[2,2]<-nrow(dataclasse)-as.numeric(as.vector(x[ligne,ncol(x)]))-conttable[2,1]
			chiresult<-chisq.test(conttable,correct=FALSE)
			if (is.na(chiresult$p.value)) {
				chiresult$p.value<-1
				chiresult$statistic<-0
				china=TRUE
			}
			obsv<-chiresult$expected
			tablep[ligne,classe]<-round(chiresult$p.value,digits=3)
			#tablep[ligne,classe]<-format(chiresult$p.value, scientific=TRUE)
            if (chiresult$statistic>=lim) {
				if (conttable[1,1]>obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
					prof[[classe]][nrow(prof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					prof[[classe]][nrow(prof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					prof[[classe]][nrow(prof[[classe]]),3]<-round((as.numeric(as.vector(x[ligne,classe]))/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					prof[[classe]][nrow(prof[[classe]]),4]<-round(chiresult$statistic,digits=2)
					prof[[classe]][nrow(prof[[classe]]),5]<-mod.names[ligne]
					prof[[classe]][nrow(prof[[classe]]),6]<-chiresult$p.value
				}
				else if (conttable[1,1]<obsv[1,1]){
					tablesqr[ligne,classe]<--round(chiresult$statistic,digits=3)
					aprof[[classe]][nrow(aprof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					aprof[[classe]][nrow(aprof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					aprof[[classe]][nrow(aprof[[classe]]),3]<-round((as.numeric(x[ligne,classe])/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),4]<--round(chiresult$statistic,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),5]<-mod.names[ligne]
					aprof[[classe]][nrow(aprof[[classe]]),6]<-chiresult$p.value
				}
				#pour gerer le cas avec une seule v et par exemple
				else if (conttable[1,1]==obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
					prof[[classe]][nrow(prof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					prof[[classe]][nrow(prof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					prof[[classe]][nrow(prof[[classe]]),3]<-round((as.numeric(as.vector(x[ligne,classe]))/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					prof[[classe]][nrow(prof[[classe]]),4]<-round(chiresult$statistic,digits=2)
					prof[[classe]][nrow(prof[[classe]]),5]<-mod.names[ligne]
					prof[[classe]][nrow(prof[[classe]]),6]<-chiresult$p.value
					aprof[[classe]][nrow(aprof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					aprof[[classe]][nrow(aprof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					aprof[[classe]][nrow(aprof[[classe]]),3]<-round((as.numeric(x[ligne,classe])/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),4]<--round(chiresult$statistic,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),5]<-mod.names[ligne]
					aprof[[classe]][nrow(aprof[[classe]]),6]<-chiresult$p.value
				}
			}else {
				if (conttable[1,1]>obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
				} else if (conttable[1,1]<obsv[1,1]){
					tablesqr[ligne,classe]<--round(chiresult$statistic,digits=3)
				}
				#pour gerer le cas avec une seule v et par exemple
				else if (conttable[1,1]==obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
				}
			}
			#				}
		}
	}
	for (classe in 1:clusternb) {
		if (length(prof[[classe]])!=0) {
			prof[[classe]]<-prof[[classe]][order(prof[[classe]][,4],decreasing=TRUE),]
		}
		if (length(aprof[[classe]])!=0) {
			aprof[[classe]]<-aprof[[classe]][order(aprof[[classe]][,4]),]	
		}
	}
	print('fini build prof')
	output<-list()
	output[[1]]<-tablep
	output[[2]]<-tablesqr
	output[[3]]<-afctablesum
	output[[4]]<-prof
	output[[5]]<-aprof
	output
}


build.pond.prof <- function(mat, lim = 2) {
	mat<-as.matrix(mat)
	mod.names<-rownames(mat)
	scol<-colSums(mat)
	srow<-rowSums(mat)
	tot<-sum(srow)
	tablesqr<-mat
	tablep<-mat
	prof<-list()
	aprof<-list()
    clusternb <- ncol(mat)
    x <- cbind(mat, rowSums(mat))
	for (classe in 1:clusternb) {
		prof[[classe]]<-data.frame()
		aprof[[classe]]<-data.frame()
	}

    for (ligne in 1:nrow(mat)) {
        for(classe in 1:ncol(mat)) {
            tb <- matrix(0,2,2)
            tb[1,1] <- mat[ligne,classe]
            tb[1,2] <- srow[ligne] - tb[1,1]
            tb[2,1] <- scol[classe] - tb[1,1]
            tb[2,2] <- tot - srow[ligne] - tb[2,1]
            chiresult <- MyChiSq(tb)
            if (is.na(chiresult$p.value)) {
				chiresult$p.value<-1
				chiresult$statistic<-0
			}
            tablep[ligne,classe]<-round(chiresult$p.value,digits=3)
            conttable<-tb
            obsv <- chiresult$expected
            if (chiresult$statistic>=lim) {
				if (conttable[1,1]>obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
					prof[[classe]][nrow(prof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					prof[[classe]][nrow(prof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					prof[[classe]][nrow(prof[[classe]]),3]<-round((as.numeric(as.vector(x[ligne,classe]))/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					prof[[classe]][nrow(prof[[classe]]),4]<-round(chiresult$statistic,digits=2)
					prof[[classe]][nrow(prof[[classe]]),5]<-mod.names[ligne]
					prof[[classe]][nrow(prof[[classe]]),6]<-chiresult$p.value
				}
				else if (conttable[1,1]<obsv[1,1]){
					tablesqr[ligne,classe]<--round(chiresult$statistic,digits=3)
					aprof[[classe]][nrow(aprof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					aprof[[classe]][nrow(aprof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					aprof[[classe]][nrow(aprof[[classe]]),3]<-round((as.numeric(x[ligne,classe])/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),4]<--round(chiresult$statistic,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),5]<-mod.names[ligne]
					aprof[[classe]][nrow(aprof[[classe]]),6]<-chiresult$p.value
				}
				#pour gerer le cas avec une seule v et par exemple
				else if (conttable[1,1]==obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
					prof[[classe]][nrow(prof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					prof[[classe]][nrow(prof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					prof[[classe]][nrow(prof[[classe]]),3]<-round((as.numeric(as.vector(x[ligne,classe]))/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					prof[[classe]][nrow(prof[[classe]]),4]<-round(chiresult$statistic,digits=2)
					prof[[classe]][nrow(prof[[classe]]),5]<-mod.names[ligne]
					prof[[classe]][nrow(prof[[classe]]),6]<-chiresult$p.value
					aprof[[classe]][nrow(aprof[[classe]])+1,1]<-as.numeric(x[ligne,classe])
					aprof[[classe]][nrow(aprof[[classe]]),2]<-as.numeric(as.vector(x[ligne,ncol(x)]))
					aprof[[classe]][nrow(aprof[[classe]]),3]<-round((as.numeric(x[ligne,classe])/as.numeric(as.vector(x[ligne,ncol(x)])))*100,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),4]<--round(chiresult$statistic,digits=2)
					aprof[[classe]][nrow(aprof[[classe]]),5]<-mod.names[ligne]
					aprof[[classe]][nrow(aprof[[classe]]),6]<-chiresult$p.value
				}
			}else {
				if (conttable[1,1]>obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
				} else if (conttable[1,1]<obsv[1,1]){
					tablesqr[ligne,classe]<--round(chiresult$statistic,digits=3)
				}
				#pour gerer le cas avec une seule v et par exemple
				else if (conttable[1,1]==obsv[1,1]) {
					tablesqr[ligne,classe]<-round(chiresult$statistic,digits=3)
				}
			}

        }
    }
	for (classe in 1:clusternb) {
		if (length(prof[[classe]])!=0) {
			prof[[classe]]<-prof[[classe]][order(prof[[classe]][,4],decreasing=TRUE),]
		}
		if (length(aprof[[classe]])!=0) {
			aprof[[classe]]<-aprof[[classe]][order(aprof[[classe]][,4]),]	
		}
	}
	output<-list()
	output[[1]]<-tablep
	output[[2]]<-tablesqr
	output[[3]]<-x
	output[[4]]<-prof
	output[[5]]<-aprof
	output
}

    
    
