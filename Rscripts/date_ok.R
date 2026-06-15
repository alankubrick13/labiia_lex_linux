

load('mariagepourtousnov-jui_corpus_corpus_1/mariagepourtousnov-jui_corpus_alceste_2/RData.RData')
load('mariagegaynov-jui_corpus_corpus_1/mariagegaynov-jui_corpus_alceste_3/RData.RData')
load('mariagehomonov-jui_corpus_corpus_1/mariagehomonov-jui_corpus_alceste_2/RData.RData')

dpt <- chistabletot[tc,]
#dpt <- chistabletot[debet:nrow(chistabletot),]
dd <-rownames(dpt)
dd <- strptime(dd, "*date_%Y-%m-%d")
dd <- strptime(dd, "%Y-%m-%d")
dd <- cbind(as.character(dd), dpt)
dd <- dd[order(dd[,1]),]
dd <- add.missing.date(dd,c.dates = 1, datedeb=c(07,11,2012), datefin=c(31,07,2013))

#tot <- afctable[debet:nrow(afctable),]
tot <- afctable[tc,]
tt <- rownames(tot)
tt <- strptime(tt, "*date_%Y-%m-%d")
tt <- strptime(tt, "%Y-%m-%d")
tt <- cbind(as.character(tt), tot)
tt <- tt[order(tt[,1]),]
tt <- add.missing.date(tt, c.dates = 1, datedeb=c(07,11,2012), datefin=c(31,07,2013))

rn <- tt[,1]
tt <- tt[,-1]
tt <- apply(tt, 2, as.numeric)
rownames(tt) <- rn
tcp <- rowSums(tt)
ptc <- tcp/sum(tcp)

ptt <- prop.table(as.matrix(tt), 1)

tcl <- table(classes)
z <- which(names(tcl)=="0")
if (length(z) != 0) {tcl <- tcl[-z]}
tclp <- tcl/sum(tcl)



rn <- dd[,1]
dd <- dd[,-1]
dd <- apply(dd,2, as.numeric)
rownames(dd) <- rn



library(ape)


tree1 <- tree.cut1$tree.cl
tree1 <- compute.brlen(tree1)
tree1 <- as.hclust(tree1)



dd <- t(dd)

cc <- dd
cc[which(dd <= (-3.84))] <- 1
cc[which((dd > (-3.84)) & (dd < 3.84))] <- 2
cc[which(dd >= 3.84)] <- 3
library(RColorBrewer)
#col <- brewer.pal(3, 'Reds')
#col <- c('red', 'green', 'blue')
col <- c('black', 'black', 'red')
col <- c('white', 'white', 'blue')
col <- col[cc]


clod <- rev(as.numeric(tree.cut1$tree.cl$tip.label))

heatmap(as.matrix(dd[as.numeric(tree.cut1$tree.cl$tip.label),]), Colv=NA, Rowv=as.dendrogram(tree1), col=col)

png('cl_dates_homo.png', h=1000, w=2500)
alphas <- seq(0,1, length.out=length(breaks))
#par(mfrow=c(nrow(dd),1))
par(mar=c(3,3,3,3))
layout(matrix(c(rep(1,nrow(dd)),c(2:(nrow(dd)+1)),c(rep(nrow(dd)+2, nrow(dd)))),ncol=3), heights=tclp[clod], widths=c(0.05,0.92,0.03))
par(mar=c(0,0,0,0))
plot.phylo(tree.cut1$tree.cl,label.offset=0.1)
for (i in clod) {
    print(i)
    par(mar=c(0,0,0,0))
    lcol <- cut(dd[i,], breaks, include.lowest=TRUE)
    ulcol <- names(table(lcol))
    lcol <- as.character(lcol)
    for (j in 1:length(ulcol)) {
        lcol[which(lcol==ulcol[j])] <- j
    }
    lcol <- as.numeric(lcol)

    #lcol[which(lcol <= 9)] <- 1

    mcol <- rainbow(nrow(dd))[i]
    last.col <- NULL
    for (k in alphas) {
        last.col <- c(last.col, rgb(r=col2rgb(mcol)[1]/255, g=col2rgb(mcol)[2]/255, b=col2rgb(mcol)[3]/255, a=k))
    }
    print(last.col)

    barplot(rep(1,ncol(dd)), width=ptc, names.arg=FALSE, axes=FALSE, col=last.col[lcol], border=rgb(r=0, g=0, b=0, a=0.3))
#val2col(dd[i,], col=heat.colors(30)), border=NA)
}
plot.new()
legend('right', as.character(lk), fill=last.col)

dev.off()


layout(matrix(c(rep(1,nrow(dd)),c(2:(nrow(dd)+1)),c(rep(nrow(dd)+2, nrow(dd)))),ncol=3), heights=tclp[clod], widths=c(0.05,0.92,0.03))
par(mar=c(0,0,0,0))
plot.phylo(tree.cut1$tree.cl,label.offset=0.1)
ncol <- rainbow(nrow(dd))
for (i in clod) {
    print(i)
    par(mar=c(0,0,0,0))
    barplot(dd[i,], width=ptc, names.arg=FALSE, axes=FALSE, col=ncol[i])
}




vcol <- rainbow(nrow(dd))
ncoli <- dd
for (i in 1:nrow(dd)) {
    lcol <- cut(dd[1,], breaks, include.lowest=TRUE)
    ulcol <- names(table(lcol))
    lcol <- as.character(lcol)
    rlcol <- rank()
    for (i in 1:length(ulcol)) {
        lcol[which(lcol==ulcol[i])] <- i
    }
    lcol <- as.numeric(lcol)
    for (j in 1:ncol(dd)) {
        if (dd[i,j] < 3.84) {
            ncoli[i,j] <- rgb(r=col2rgb(vcol[i])[1]/255, g=col2rgb(vcol[i])[2]/255, b=col2rgb(vcol[i])[3]/255, a=0.2)
        } else {
            ncoli[i,j] <- rgb(r=col2rgb(vcol[i])[1]/255, g=col2rgb(vcol[i])[2]/255, b=col2rgb(vcol[i])[3]/255, a=1)
        }
    }
}

barplot(t(ptt)[as.numeric(tree.cut1$tree.cl$tip.label),], col=rainbow(ncol(ptt))[as.numeric(tree.cut1$tree.cl$tip.label)], width=ptc, las=3, space=0.05, cex.axis=0.7, border=NA)

layout(matrix(c(1:nrow(ptt)), nrow=1),  widths=ptc)
od <- as.numeric(tree.cut1$tree.cl$tip.label)
colod = rainbow(ncol(ptt))[od]
for (i in 1:ncol(ptt)) {
    par(mar=c(0,0,0,0))
    barplot(as.matrix(ptt[i,od], ncol=1), col=colod, axes=FALSE)
}

k <- 1e-02
lcol <- NULL
lk <- k
for (i in 1:5) {
    lcol <- c(lcol, qchisq(1-k,1))
    k <- k/10
    lk <- c(lk,k)
}
lcol <- c(3.84, lcol)
lcol <- c(-Inf,lcol)
lcol <- c(lcol, Inf)
lk <- c(0.05,lk)
#lcol <- c(-rev(lcol), lcol)
#lk <- c(-rev(lk), lk)
#lcol <- c(min(dd), lcol)
#lk <- c(1, lk)
#breaks <- c(lcol, max(dd))
breaks <- lcol

lcol <- cut(dd[1,], breaks)
ulcol <- names(table(lcol))
lcol <- as.character(lcol)
for (i in 1:length(ulcol)) {
    lcol[which(lcol==ulcol[i])] <- i
}
lcol <- as.numeric(lcol)


make.chi <- function(x) {
    rs <- rowSums(x)
    cs <- colSums(x)
    n <- sum(x)
    
}



select.chi.classe <- function(tablechi, nb, active = TRUE) {
    rowkeep <- NULL
    if (active & !is.null(debsup)) {
        print(debsup)
        print('###############################################################@')
        tablechi <- tablechi[1:(debsup-1),]
    } else if (!active & !is.null(debsup)) {
        tablechi <- tablechi[debsup:(debet-1),]
    }
    if (nb > nrow(tablechi)) {
        nb <- nrow(tablechi)
    }
    for (i in 1:ncol(tablechi)) {
        rowkeep <- append(rowkeep,order(tablechi[,i], decreasing = TRUE)[1:nb])
    }
    rowkeep <- unique(rowkeep)
    rowkeep
}


plot.dendro.cloud <- function(tree, classes, chisqtable, nbbycl = 60, type.dendro = "phylogram", max.cex=2, min.cex=0.3, from.cmd = FALSE, bw = FALSE, lab = NULL, do.cloud=FALSE) {
    library(wordcloud)
    library(ape)
    classes<-classes[classes!=0]
	classes<-as.factor(classes)
	sum.cl<-as.matrix(summary(classes, maxsum=1000000))
	sum.cl<-(sum.cl/colSums(sum.cl)*100)
	sum.cl<-round(sum.cl,2)
	sum.cl<-cbind(sum.cl,as.matrix(100-sum.cl[,1]))
    sum.cl <- sum.cl[,1]
    tree.order<- as.numeric(tree$tip.label)
	vec.mat<-NULL

	for (i in 1:length(sum.cl)) vec.mat<-append(vec.mat,1)
	v<-2
	for (i in 1:length(sum.cl)) {
		vec.mat<-append(vec.mat,v)
		v<-v+1
	}
	if (!do.cloud) {
    	layout(matrix(vec.mat,length(sum.cl),2), heights=tclp[clod], widths=c(0.15,0.85))
	} else {
		row.keep <- select.chi.classe(chisqtable, nbbycl)
		toplot <- chisqtable[row.keep,]
		lclasses <- list()
		for (classe in 1:length(sum.cl)) {
			ntoplot <- toplot[,classe]
			ntoplot <- ntoplot[order(ntoplot, decreasing = TRUE)]
			ntoplot <- round(ntoplot, 0)
			ntoplot <- ntoplot[1:nbbycl]
			ntoplot <- ntoplot[order(ntoplot)]
			#ntoplot <- ifelse(length(ntoplot) > nbbycl, ntoplot[1:nbbycl], ntoplot)
			lclasses[[classe]] <- ntoplot
		}
		sup.keep <- select.chi.classe(chisqtable, nbbycl, active = FALSE)
		toplot.sup <- chisqtable[debsup:(debet+1),]
		toplot.sup <- toplot.sup[sup.keep, ]
		lsup <- list()
		for (classe in 1:length(sum.cl)) {
			ntoplot <- toplot.sup[,classe]
			ntoplot <- ntoplot[order(ntoplot, decreasing = TRUE)]
			ntoplot <- round(ntoplot, 0)
			ntoplot <- ntoplot[1:nbbycl]
			ntoplot <- ntoplot[order(ntoplot)]
			#ntoplot <- ifelse(length(ntoplot) > nbbycl, ntoplot[1:nbbycl], ntoplot)
			lsup[[classe]] <- ntoplot
		}
    	layout(matrix(c(rep(1,nrow(dd)),c(2:(nrow(dd)+1)),c((nrow(dd)+2):(2*nrow(dd)+1)), c((2*nrow(dd)+2):(3*nrow(dd)+1))),ncol=4), heights=tclp[clod], widths=c(0.05,0.05,0.05, 0.85))
	}
	
    if (! bw) {
        col <- rainbow(length(sum.cl))[as.numeric(tree$tip.label)]
        colcloud <- rainbow(length(sum.cl))
    }
    par(mar=c(0,0,0,0))
    label.ori<-tree[[2]]
    if (!is.null(lab)) {
        tree$tip.label <- lab
    } else {
	    tree[[2]]<-paste('classe ',tree[[2]])
    }
	plot.phylo(tree,label.offset=0.1,tip.col=col, type=type.dendro)
	if (do.cloud) {
	    for (i in rev(tree.order)) {
	        par(mar=c(0,0,1,0),cex=0.9)
	        wordcloud(names(lclasses[[i]]), lclasses[[i]], scale = c(max.cex, min.cex), random.order=FALSE, colors = colcloud[i])
	    }
	    for (i in rev(tree.order)) {
	        par(mar=c(0,0,1,0),cex=0.9)
	        wordcloud(names(lsup[[i]]), lsup[[i]], scale = c(max.cex, min.cex), random.order=FALSE, colors = colcloud[i])
	    }
	}

    for (i in rev(tree.order)) {    
        par(mar=c(0,0,0,0))
        lcol <- cut(dd[i,], breaks, include.lowest=TRUE)
        ulcol <- names(table(lcol))
        lcol <- as.character(lcol)
        for (j in 1:length(ulcol)) {
            lcol[which(lcol==ulcol[j])] <- j
        }
        lcol <- as.numeric(lcol)
    
        #lcol[which(lcol <= 9)] <- 1
    
        mcol <- rainbow(nrow(dd))[i]
        last.col <- NULL
        for (k in alphas) {
            last.col <- c(last.col, rgb(r=col2rgb(mcol)[1]/255, g=col2rgb(mcol)[2]/255, b=col2rgb(mcol)[3]/255, a=k))
        }
        print(last.col)
    
        barplot(rep(1,ncol(dd)), width=ptc, names.arg=FALSE, axes=FALSE, col=last.col[lcol], border=rgb(r=0, g=0, b=0, a=0.3))

    }
}


filename.to.svg <- function(filename) {
	filename <- gsub('.png', '.svg', filename)
	return(filename)
}

open_file_graph <- function (filename, width=800, height = 800, quality = 100, svg = FALSE) {
	if (Sys.info()["sysname"] == 'Darwin') {
        width <- width/74.97
        height <- height/74.97
        if (!svg) {
		    quartz(file = filename, type = 'png', width = width, height = height)
        } else {
            svg(filename.to.svg(filename), width=width, height=height)
        }
	} else {
        if (svg) {
            svg(filename.to.svg(filename), width=width/74.97, height=height/74.97)
        } else {
		    png(filename, width=width, height=height)#, quality = quality)
        }
	}
}



open_file_graph('cl_cloud_dates_gay.png', height=900, width=2500, svg=TRUE)
plot.dendro.cloud(tree.cut1$tree.cl, classes, chistabletot, from.cmd=TRUE)

dev.off()
