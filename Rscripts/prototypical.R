
norm.vec <- function(v, min, max) {

  vr <- range(v)
  if (vr[1]==vr[2]) {
    fac <- 1
  } else {
    fac <- (max-min)/(vr[2]-vr[1])
  }
  (v-vr[1]) * fac + min
}


#x a table with freq and rank, rownames are words

prototypical <- function(x, mfreq = NULL, mrank = NULL, cexrange=c(0.8, 3), cexalpha = c(0.5, 1), labfreq = TRUE, labrank = TRUE, cloud = TRUE, type = 'classical') {
    library(wordcloud)
    if (is.null(mfreq)) {
        mfreq <- sum(x[,1]) / nrow(x)
    }
    if (is.null(mrank)) {
        mrank <- sum(x[,1] * x[,2]) / sum(x[,1])
    }
    print(mfreq)
    print(mrank)

    x <- x[order(x[,1], decreasing = TRUE),]
    x[,2] <- round(x[,2],1)
    ZN <- which(x[,1] >= mfreq & x[,2] <= mrank)
    FP <- which(x[,1] >= mfreq & x[,2] > mrank)
    SP <- which(x[,1] < mfreq & x[,2] > mrank)
    CE <- which(x[,1] < mfreq & x[,2] <= mrank)
    mfreq <- round(mfreq, 2)
    mrank <- round(mrank, 2)
    toplot <- list(ZN, FP, SP, CE)
    labcex <- norm.vec(x[,1], cexrange[1], cexrange[2])
    labalpha <- norm.vec(x[,2], cexalpha[2], cexalpha[1])
    labalpha <- rgb(0.1,0.2,0.1, labalpha)
	labcol <- rep('black', nrow(x))
	labcol[FP] <- 'red'
	labcol[SP] <- 'green'
	labcol[ZN] <- 'blue'
    ti <- c("Zone du noyau", "Première périphérie", "Seconde périphérie", "Elements contrastés")
	if (type == 'classical') {
	    par(oma=c(1,3,3,1))
	    layout(matrix(c(1,4,2,3), nrow=2))
	    for (i in 1:length(toplot)) {
	        rtoplot <- toplot[[i]]
	        if (length(rtoplot)) {
	            par(mar=c(0,0,2,0))
	            if (cloud) {
	                labels <- paste(rownames(x)[rtoplot], x[rtoplot,1], x[rtoplot,2], sep='-')
	                wordcloud(labels, x[rtoplot,1], scale = c(max(labcex[rtoplot]), min(labcex[rtoplot])), color = labalpha[rtoplot], random.order=FALSE, rot.per = 0)
	                box()
	            } else {
	                yval <- 1.1
	                plot(0,0,pch='', axes = FALSE)
	                k<- 0
	                for (val in rtoplot) {
	                    yval <- yval-(strheight(rownames(x)[val],cex=labcex[val])+0.02)
	                    text(-0.9, yval, paste(rownames(x)[val], x[val,1], x[val,2], sep = '-'), cex = labcex[val], col = labalpha[val], adj=0)
	                }
	                box()
	            }
	            title(ti[i])
	        }
	    }
	    mtext(paste('<', mfreq, '  Fréquences  ', '>=', mfreq, sep = ' '), side=2, line=1, cex=1, col="red", outer=TRUE)
	    mtext(paste('<=', mrank,  '  Rangs  ', '>', mrank, sep = ' '), side=3, line=1, cex=1, col="red", outer=TRUE)
	} else if (type == 'plan') {
		par(oma=c(3,3,1,1))
		textplot(x[,1], x[,2], rownames(x), cex=labcex, xlim=c(min(x[,1])-nrow(x)/3, max(x[,1])+5), ylim = c(min(x[,2])-0.2, max(x[,2])+0.5), col=labcol, xlab="", ylab="")
	    abline(v=mfreq)
		abline(h=mrank)
		legend('topright', ti, fill=c('blue', 'red', 'green', 'black'))
		mtext(paste('<', mfreq, '  Fréquences  ', '>=', mfreq, sep = ' '), side=1, line=1, cex=1, col="red", outer=TRUE)
		mtext(paste('<=', mrank,  '  Rangs  ', '>', mrank, sep = ' '), side=2, line=1, cex=1, col="red", outer=TRUE)		
	}
}

intervalle.freq <- function(x, SX=NULL) {
	errorn <- (x/SX) + (1.96 * sqrt(((x/SX) * (1-(x/SX))/SX)))
	print(errorn)
}
