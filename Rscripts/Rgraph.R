############FIXME##################
#PlotDendroComp <- function(chd,filename,reso) {
#   jpeg(filename,res=reso)
#   par(cex=PARCEX)
#   plot(chd,which.plots=2, hang=-1)
#   dev.off()
#}
#
#PlotDendroHori <- function(dendrocutupper,filename,reso) {
#   jpeg(filename,res=reso)
#   par(cex=PARCEX)
#   nP <- list(col=3:2, cex=c(0.5, 0.75), pch= 21:22, bg= c('light blue', 'pink'),lab.cex = 0.75, lab.col = 'tomato')
#   plot(dendrocutupper,nodePar= nP, edgePar = list(col='gray', lwd=2),horiz=TRUE, center=FALSE)
#   dev.off()
#}

PlotDendroCut <- function(chd,filename,reso,clusternb) {   
   h.chd <- as.hclust(chd)
   memb <- cutree(h.chd, k = clusternb)
   cent <- NULL
   for(k in 1:clusternb){
       cent <- rbind(cent, k)
   }
   h.chd1 <- hclust(dist(cent)^2, method = 'cen', members = table(memb))
   h.chd1$labels <- sprintf('CL %02d',1:clusternb)
   nP <- list(col=3:2, cex=c(2.0, 0.75), pch= 21:22, bg= c('light blue', 'pink'),lab.cex = 0.75, lab.col = 'tomato')
   jpeg(filename,res=reso)
   par(cex=PARCEX)
   plot(h.chd1, nodePar= nP, edgePar = list(col='gray', lwd=2), horiz=TRUE, center=TRUE, hang= -1)
   dev.off()
}

#PlotAfc<- function(afc, filename, width=800, height=800, quality=100, reso=200, toplot=c('all','all'), PARCEX=PARCEX) {
#	if (Sys.info()["sysname"]=='Darwin') {
#		width<-width/74.97
#		height<-height/74.97
#		quartz(file=filename,type='jpeg',width=width,height=height)
#	} else {
#		jpeg(filename,width=width,height=height,quality=quality,res=reso)
#	}
#	par(cex=PARCEX)
#	plot(afc,what=toplot,labels=c(1,1),contrib=c('absolute','relative'))
#	dev.off()
#}

PlotAfc2dCoul<- function(afc,chisqrtable,filename, what='coord',col=FALSE, axetoplot=c(1,2), deb=0,fin=0, width=900, height=900, quality=100, reso=200, parcex=PARCEX, xlab = NULL, ylab = NULL, xmin=NULL, xmax=NULL, ymin=NULL, ymax=NULL, active = TRUE) {
	if (col) {
		if (what == 'coord') {
			rowcoord <- as.matrix(afc$colcoord)
		} else {
			rowcoord <- as.matrix(afc$colcrl)
		}
	} else {
		if (what == 'coord') {
			rowcoord <- as.matrix(afc$rowcoord)
		} else {
			rowcoord <- as.matrix(afc$rowcrl)
		}
	}
	x <- axetoplot[1]
	y <- axetoplot[2]
	if (col)
		rownames(rowcoord) <- afc$colnames
	if (!col){
		rownames(rowcoord) <- afc$rownames
		rowcoord <- as.matrix(rowcoord[deb:fin,])
		chitable<- as.matrix(chisqrtable[deb:fin,])
		#row_keep <- select_point_nb(chitable,15)
	}
	if (ncol(rowcoord) == 1) {
		rowcoord <- t(rowcoord)
	}
	clnb <- ncol(chisqrtable)
	
	if (!col) {
        classes <- as.matrix(apply(chitable,1,which.max))
        cex.par <- norm.vec(apply(chitable,1,max), 0.8,3)
        row.keep <- select.chi.classe(chitable, 80, active=active)
        rowcoord <- rowcoord[row.keep,]
        classes <- classes[row.keep]
        cex.par <- cex.par[row.keep]
	} else {
        classes <- 1:clnb
        cex.par <- rep(1,clnb)
    }
    if (is.null(xmin)) {
        table.in <- rowcoord
        xminmax <- c(min(table.in[,1], na.rm = TRUE) + ((max(cex.par)/10) * min(table.in[,1], na.rm = TRUE)), max(table.in[,1], na.rm = TRUE) + ((max(cex.par)/10) * max(table.in[,1], na.rm = TRUE)))
        xmin <- xminmax[1]
        xmax <- xminmax[2]
        yminmax <- c(min(table.in[,2], na.rm = TRUE) + ((max(cex.par)/10) * min(table.in[,2], na.rm = TRUE)), max(table.in[,2], na.rm = TRUE) + ((max(cex.par)/10) * max(table.in[,2], na.rm = TRUE)))
        ymin <- yminmax[1]
        ymax <- yminmax[2]
     }
	#ntabtot <- cbind(rowcoord, classes)
	#if (!col) ntabtot <- ntabtot[row_keep,]
    xlab <- paste('fator ', x, ' -')
    ylab <- paste('fator ', y, ' -')
    xlab <- paste(xlab,round(afc_table$facteur[x,2],2),sep = ' ')
    xlab <- paste(xlab,' %%',sep = '')
    ylab <- paste(ylab,round(afc_table$facteur[y,2],2),sep = ' ')
    ylab <- paste(ylab,' %%',sep = '')

	open_file_graph(filename, width = width, height = height)
	par(cex=PARCEX)
    table.in <- rowcoord[order(cex.par, decreasing = TRUE),]
    classes <- classes[order(cex.par, decreasing = TRUE)]
    cex.par <- cex.par[order(cex.par, decreasing = TRUE)]
    table.out <- stopoverlap(table.in, cex.par=cex.par, xlim = c(xmin,xmax), ylim = c(ymin,ymax))
	table.in <- table.out$toplot
    notplot <- table.out$notplot
    if (! is.null(notplot)) {
        write.csv2(notplot, file = paste(filename, '_notplotted.csv', sep = ''))
    }
    classes <- classes[table.in[,4]]
    cex.par <- cex.par[table.in[,4]]
    make_afc_graph(table.in, classes, clnb, xlab, ylab, cex.txt = cex.par, xminmax=c(xmin,xmax), yminmax=c(ymin,ymax))
    xyminmax <- list(yminmax = c(ymin,ymax), xminmax = c(xmin,xmax))
    xyminmax 
	#plot(rowcoord[,x],rowcoord[,y], pch='', xlab = xlab, ylab = ylab)
	#abline(h=0,v=0)
	#for (i in 1:clnb) {
	#	ntab <- subset(ntabtot,ntabtot[,ncol(ntabtot)] == i)
	#	if (nrow(ntab) != 0)
	#		text(ntab[,x],ntab[,y],rownames(ntab),col=rainbow(clnb)[i])
	#}
	#dev.off()
}

filename.to.svg <- function(filename) {
    filename <- gsub('.png', '.svg', filename)
    return(filename)
}

open_file_graph <- function (filename, width=800, height = 800, quality = 100, svg = FALSE, dpi = 200) {
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
            opened <- FALSE
            if (capabilities("cairo")) {
                opened <- tryCatch({
                    png(
                        filename,
                        width = width,
                        height = height,
                        units = "px",
                        res = dpi,
                        type = "cairo-png",
                        antialias = "subpixel",
                        bg = "white"
                    )
                    TRUE
                }, error = function(e) FALSE)
            }
            if (!opened) {
		        png(
                    filename,
                    width = width,
                    height = height,
                    units = "px",
                    res = dpi,
                    bg = "white"
                )
            }
        }
	}
}

#################################################@@
#from wordcloud
overlap <- function(x1, y1, sw1, sh1, boxes) {
    use.r.layout <- FALSE
	if(!use.r.layout)
		return(.overlap(x1,y1,sw1,sh1,boxes))
	s <- 0
	if (length(boxes) == 0) 
		return(FALSE)
	for (i in c(last,1:length(boxes))) {
		bnds <- boxes[[i]]
		x2 <- bnds[1]
		y2 <- bnds[2]
		sw2 <- bnds[3]
		sh2 <- bnds[4]
		if (x1 < x2) 
			overlap <- x1 + sw1 > x2-s
		else 
			overlap <- x2 + sw2 > x1-s
		
		if (y1 < y2) 
			overlap <- overlap && (y1 + sh1 > y2-s)
		else 
			overlap <- overlap && (y2 + sh2 > y1-s)
		if(overlap){
			last <<- i
			return(TRUE)
		}
	}
	FALSE
}

.overlap <- function(x11,y11,sw11,sh11,boxes1){
	if (as.character(packageVersion('wordcloud')) >= '2.6') {
		.Call("_wordcloud_is_overlap", x11,y11,sw11,sh11,boxes1)
	} else {
		.Call("is_overlap",x11,y11,sw11,sh11,boxes1)
	}
}
########################################################
stopoverlap <- function(x, cex.par = NULL, xlim = NULL, ylim = NULL) {
#from wordcloud
    library(wordcloud)
    tails <- "g|j|p|q|y"
    rot.per <- 0 
    last <- 1
    thetaStep <- .1
    rStep <- .5
    toplot <- NULL
    notplot <- NULL

#    plot.new()
    plot(x[,1],x[,2], pch='', xlim = xlim, ylim = ylim)

    words <- rownames(x)
    if  (is.null(cex.par))  {
        size <- rep(0.9, nrow(x))
    } else {
        size <- cex.par
    }
    #cols <- rainbow(clnb)
    boxes <- list()
    for (i in 1:nrow(x)) {
        rotWord <- runif(1)<rot.per
        r <-0
		theta <- runif(1,0,2*pi)
		x1<- x[i,1] 
		y1<- x[i,2]
		wid <- strwidth(words[i],cex=size[i])
		ht <- strheight(words[i],cex=size[i])
		isOverlaped <- TRUE
		while(isOverlaped){
			if(!overlap(x1-.5*wid,y1-.5*ht,wid,ht, boxes)) { #&&
                toplot <- rbind(toplot, c(x1, y1, size[i], i)) 
				#text(x1,y1,words[i],cex=size[i],offset=0,srt=rotWord*90,
				#		col=cols[classes[i]])
				boxes[[length(boxes)+1]] <- c(x1-.5*wid,y1-.5*ht,wid,ht)
				isOverlaped <- FALSE
			} else {
				if(r>sqrt(.5)){
					#print(paste(words[i], "could not be fit on page. It will not be plotted."))
                    notplot <- rbind(notplot,c(words[i], x[i,1], x[i,2], size[i], i))
					isOverlaped <- FALSE
				}
				theta <- theta+thetaStep
				r <- r + rStep*thetaStep/(2*pi)
                x1 <- x[i,1]+r*cos(theta)
				y1 <- x[i,2]+r*sin(theta)
			}
		}
    }
	nbnot <- nrow(notplot)
	print(paste(nbnot, ' not plotted'))
    row.names(toplot) <- words[toplot[,4]]
    return(list(toplot = toplot, notplot = notplot))
}
###############################################################################

getwordcloudcoord <- function(words,freq,scale=c(4,.5),min.freq=3,max.words=Inf,random.order=TRUE,random.color=FALSE,
		rot.per=.1,colors="black",ordered.colors=FALSE,use.r.layout=FALSE,fixed.asp=TRUE,...) { 
	tails <- "g|j|p|q|y"
	last <- 1
	
	overlap <- function(x1, y1, sw1, sh1) {
		if(!use.r.layout)
			return(.overlap(x1,y1,sw1,sh1,boxes))
		s <- 0
		if (length(boxes) == 0) 
			return(FALSE)
		for (i in c(last,1:length(boxes))) {
			bnds <- boxes[[i]]
			x2 <- bnds[1]
			y2 <- bnds[2]
			sw2 <- bnds[3]
			sh2 <- bnds[4]
			if (x1 < x2) 
				overlap <- x1 + sw1 > x2-s
			else 
				overlap <- x2 + sw2 > x1-s
			
			if (y1 < y2) 
				overlap <- overlap && (y1 + sh1 > y2-s)
			else 
				overlap <- overlap && (y2 + sh2 > y1-s)
			if(overlap){
				last <<- i
				return(TRUE)
			}
		}
		FALSE
	}
	
	ord <- rank(-freq, ties.method = "random")
	words <- words[ord<=max.words]
	freq <- freq[ord<=max.words]


	ord <- order(freq,decreasing=TRUE)
	words <- words[ord]
	freq <- freq[ord]
	words <- words[freq>=min.freq]
	freq <- freq[freq>=min.freq]
	if (ordered.colors) {
		colors <- colors[ord][freq>=min.freq]
	}
	
	thetaStep <- .1
	rStep <- .05
	plot.new()

	normedFreq <- freq/max(freq)
	size <- (scale[1]-scale[2])*normedFreq + scale[2]
	boxes <- list()
	toplot <- NULL	
	
	
	for(i in 1:length(words)){
		rotWord <- runif(1)<rot.per
		r <-0
		theta <- runif(1,0,2*pi)
		x1<-.5
		y1<-.5
		wid <- strwidth(words[i],cex=size[i],...)
		ht <- strheight(words[i],cex=size[i],...)
		#mind your ps and qs
		if(grepl(tails,words[i]))
			ht <- ht + ht*.2
		if(rotWord){
			tmp <- ht
			ht <- wid
			wid <- tmp	
		}
		isOverlaped <- TRUE
		while(isOverlaped){
			if(!overlap(x1-.5*wid,y1-.5*ht,wid,ht) &&
					x1-.5*wid>0 && y1-.5*ht>0 &&
					x1+.5*wid<1 && y1+.5*ht<1){
				toplot <- rbind(toplot, c(x1,y1,size[i], i))
				boxes[[length(boxes)+1]] <- c(x1-.5*wid,y1-.5*ht,wid,ht)
				isOverlaped <- FALSE
			}else{
				if(r>sqrt(.5)){
					warning(paste(words[i],
									"could not be fit on page. It will not be plotted."))
					isOverlaped <- FALSE
				}
				theta <- theta+thetaStep
				r <- r + rStep*thetaStep/(2*pi)
				x1 <- .5+r*cos(theta)
				y1 <- .5+r*sin(theta)
			}
		}
	}
	toplot <- cbind(toplot,norm.vec(freq[toplot[,4]], 1, 50))
	row.names(toplot) <- words[toplot[,4]]
	toplot <- toplot[,-4]
	return(toplot)
}

new_tree_tot <- function(chd) {
	lf <- chd$list_fille
	m <- matrix(0, ncol=2)
	for (val in 1:length(lf)) {
		if (! is.null(lf[[val]])) {
			print(c(val,lf[[val]][1]))
			m <- rbind(m, c(val,lf[[val]][1]))
			m <- rbind(m, c(val,lf[[val]][2]))
		}
	}
	m[-1,]
}

make_tree_tot <- function (chd) {
	library(ape)
	lf<-chd$list_fille
	clus<-'a1a;'
	for (i in 1:length(lf)) {
		if (!is.null(lf[[i]])) {
			clus<-gsub(paste('a',i,'a',sep=''),paste('(','a',lf[[i]][1],'a',',','a',lf[[i]][2],'a',')',sep=''),clus)
        }
	}
	dendro_tuple <- clus
	clus <- gsub('a','',clus)
	tree.cl <- read.tree(text = clus)
	res<-list(tree.cl = tree.cl, dendro_tuple = dendro_tuple)
	res
}

make_dendro_cut_tuple <- function(dendro_in, coordok, classeuce, x, nbt = 9) {
	library(ape)
	dendro<-dendro_in
	i <- 0
	for (cl in coordok[,x]) {
		i <- i + 1
		fcl<-fille(cl,classeuce)
		for (fi in fcl) {
			dendro <- gsub(paste('a',fi,'a',sep=''),paste('b',i,'b',sep=''),dendro)
		}
	}
	clnb <- nrow(coordok)
    tcl=((nbt+1) *2) - 2
	for (i in 1:(tcl + 1)) {
		dendro <- gsub(paste('a',i,'a',sep=''),paste('b',0,'b',sep=''),dendro)
	}
	dendro <- gsub('b','',dendro)
	dendro <- gsub('a','',dendro)
	dendro_tot_cl <- read.tree(text = dendro)
	#FIXME
	for (i in 1:100) {
		for (cl in 1:clnb) {
			dendro <- gsub(paste('\\(',cl,',',cl,'\\)',sep=''),cl,dendro)
		}
	}
	for (i in 1:100) {
		dendro <- gsub(paste('\\(',0,',',0,'\\)',sep=''),0,dendro)
		for (cl in 1:clnb) {
			dendro <- gsub(paste('\\(',0,',',cl,'\\)',sep=''),cl,dendro)
			dendro <- gsub(paste('\\(',cl,',',0,'\\)',sep=''),cl,dendro)
		}
	}
	print(dendro)
	tree.cl <- read.tree(text = dendro)
    lab <- tree.cl$tip.label
    if ("0" %in% lab) {
        tovire <- which(lab == "0")
        tree.cl <- drop.tip(tree.cl, tip = tovire)
    }
	res <- list(tree.cl = tree.cl, dendro_tuple_cut = dendro, dendro_tot_cl = dendro_tot_cl)
	res
}

select_point_nb <- function(tablechi, nb) {
	chimax<-as.matrix(apply(tablechi,1,max))
	chimax<-cbind(chimax,1:nrow(tablechi))
	order_chi<-as.matrix(chimax[order(chimax[,1],decreasing = TRUE),])
	row_keep <- order_chi[,2][1:nb]
	row_keep
}

select_point_chi <- function(tablechi, chi_limit) {
	chimax<-as.matrix(apply(tablechi,1,max))
	row_keep <- which(chimax >= chi_limit)
	row_keep
}

select.chi.classe <- function(tablechi, nb, active = TRUE, debsup = NULL) {
    rowkeep <- NULL
    if (active && !is.null(debsup)) {
        debsup <- suppressWarnings(as.integer(debsup))
        if (!is.na(debsup) && debsup > 1 && debsup <= nrow(tablechi)) {
            tablechi <- tablechi[1:(debsup - 1), , drop = FALSE]
        }
    }
    if (nb > nrow(tablechi)) {
        nb <- nrow(tablechi)
    }
    if (nb <= 0 || nrow(tablechi) <= 0) {
        return(integer(0))
    }
    for (i in 1:ncol(tablechi)) {
        rowkeep <- append(rowkeep, order(tablechi[, i], decreasing = TRUE)[1:nb])
    }
    rowkeep <- unique(rowkeep)
    rowkeep
}

select.chi.classe.et <- function(tablechi, nb, debet = NULL){
    rowkeep <- NULL
    ntablechi <- tablechi
    if (!is.null(debet)) {
        debet <- suppressWarnings(as.integer(debet))
        if (!is.na(debet) && debet >= 1 && debet <= nrow(tablechi)) {
            ntablechi <- tablechi[debet:nrow(tablechi), , drop = FALSE]
        }
    }
    if (nb > nrow(ntablechi)) {
        nb <- nrow(ntablechi)
    }
    if (nb <= 0 || nrow(ntablechi) <= 0) {
        return(integer(0))
    }
    for (i in 1:ncol(ntablechi)) {
        rowkeep <- append(rowkeep, order(ntablechi[, i], decreasing = TRUE)[1:nb])
    }
    rowkeep <- unique(rowkeep)
    rowkeep    
}

#from summary.ca
summary.ca.dm <- function(object, scree = TRUE, ...){
  obj <- object
  nd  <- obj$nd
  if (is.na(nd)){
    nd <- 2
    } else {
    if (nd > length(obj$sv)) nd <- length(obj$sv)
    }  
 # principal coordinates:
  K   <- nd
  I   <- dim(obj$rowcoord)[1] ; J <- dim(obj$colcoord)[1]
  svF <- matrix(rep(obj$sv[1:K], I), I, K, byrow = TRUE)
  svG <- matrix(rep(obj$sv[1:K], J), J, K, byrow = TRUE)
  rpc <- obj$rowcoord[,1:K] * svF
  cpc <- obj$colcoord[,1:K] * svG

 # rows:
  r.names <- obj$rownames
  sr      <- obj$rowsup
  if (!is.na(sr[1])) r.names[sr] <- paste("(*)", r.names[sr], sep = "")
  r.mass <- obj$rowmass
  r.inr  <- obj$rowinertia / sum(obj$rowinertia, na.rm = TRUE)
  r.COR  <- matrix(NA, nrow = length(r.names), ncol = nd)
  colnames(r.COR) <- paste('COR -facteur', 1:nd, sep=' ')
  r.CTR  <- matrix(NA, nrow = length(r.names), ncol = nd)
  colnames(r.CTR) <- paste('CTR -facteur', 1:nd, sep=' ')
  for (i in 1:nd){
    r.COR[,i] <- obj$rowmass * rpc[,i]^2 / obj$rowinertia
    r.CTR[,i] <- obj$rowmass * rpc[,i]^2 / obj$sv[i]^2
    }
 # cor and quality for supplementary rows
  if (length(obj$rowsup) > 0){
    i0 <- obj$rowsup
    for (i in 1:nd){
      r.COR[i0,i] <- obj$rowmass[i0] * rpc[i0,i]^2
      r.CTR[i0,i] <- NA
    }
    }

 # columns:
  c.names <- obj$colnames
  sc      <- obj$colsup
  if (!is.na(sc[1])) c.names[sc] <- paste("(*)", c.names[sc], sep = "")
  c.mass  <- obj$colmass
  c.inr   <- obj$colinertia / sum(obj$colinertia, na.rm = TRUE)
  c.COR   <- matrix(NA, nrow = length(c.names), ncol = nd)
  colnames(c.COR) <- paste('COR -facteur', 1:nd, sep=' ')
  c.CTR   <- matrix(NA, nrow = length(c.names), ncol = nd)
  colnames(c.CTR) <- paste('CTR -facteur', 1:nd, sep=' ')
  for (i in 1:nd)
    {
    c.COR[,i] <- obj$colmass * cpc[,i]^2 / obj$colinertia
    c.CTR[,i] <- obj$colmass * cpc[,i]^2 / obj$sv[i]^2
    }
  if (length(obj$colsup) > 0){
    i0 <- obj$colsup
    for (i in 1:nd){
      c.COR[i0,i] <- obj$colmass[i0] * cpc[i0,i]^2
      c.CTR[i0,i] <- NA
      }
    }

 # scree plot:
  if (scree) {
    values     <- obj$sv^2
    values2    <- 100*(obj$sv^2)/sum(obj$sv^2)
    values3    <- cumsum(100*(obj$sv^2)/sum(obj$sv^2))
    scree.out  <- cbind(values, values2, values3)
    } else {
    scree.out <- NA
    }

  obj$r.COR <- r.COR
  obj$r.CTR <- r.CTR
  obj$c.COR <- c.COR
  obj$c.CTR <- c.CTR
  obj$facteur <- scree.out
  return(obj)
  }

create_afc_table <- function(x) {
   #x = afc
	facteur.table <- as.matrix(x$facteur)
    nd <- ncol(x$colcoord)
	rownames(facteur.table) <- paste('fator',1:nrow(facteur.table),sep = ' ')
    colnames(facteur.table) <- c('Autovalores', 'Percentuais', 'Percentual acumulado')
	ligne.table <- as.matrix(x$rowcoord)
	rownames(ligne.table) <- x$rownames
	colnames(ligne.table) <- paste('Coord. fator', 1:nd, sep=' ')
    tmp <- as.matrix(x$rowcrl)
	colnames(tmp) <- paste('Corr. fator', 1:nd, sep=' ')
	ligne.table <- cbind(ligne.table,tmp)
	ligne.table <- cbind(ligne.table, x$r.COR)
	ligne.table <- cbind(ligne.table, x$r.CTR)
	ligne.table <- cbind(ligne.table, mass = x$rowmass)
	ligne.table <- cbind(ligne.table, chi.distance = x$rowdist)
	ligne.table <- cbind(ligne.table, inertie = x$rowinertia)
    colonne.table <- x$colcoord
	rownames(colonne.table) <- paste('classe', 1:(nrow(colonne.table)),sep=' ')
	colnames(colonne.table) <- paste('Coord. fator', 1:nd, sep=' ')
    tmp <- as.matrix(x$colcrl)
	colnames(tmp) <- paste('Corr. fator', 1:nd, sep=' ')
	colonne.table <- cbind(colonne.table, tmp)
	colonne.table <- cbind(colonne.table, x$c.COR)
	colonne.table <- cbind(colonne.table, x$c.CTR)
	colonne.table <- cbind(colonne.table, mass = x$colmass)
	colonne.table <- cbind(colonne.table, chi.distance = x$coldist)
	colonne.table <- cbind(colonne.table, inertie = x$colinertia)
    res <- list(facteur = facteur.table, ligne = ligne.table, colonne = colonne.table)
	res
}

is.yellow <- function(my.color) {
    if ((my.color[1] > 200) & (my.color[2] > 200) & (my.color[3] < 100)) {
        return(TRUE)
    } else {
        return(FALSE)
    }
}

del.yellow <- function(colors) {
    rgbs <- col2rgb(colors)
    tochange <- apply(rgbs, 2, is.yellow)
    tochange <- which(tochange)
    if (length(tochange)) {
        gr.col <- colorRampPalette(c("#D4A017", "#B8860B"))(length(tochange))
    }
    compt <- 1
    for (val in tochange) {
        colors[val] <- gr.col[compt]
        compt <- compt + 1
    }
    colors
}

safe.class.palette <- function(n) {
    base <- c(
        "#B22222", "#1E3A8A", "#0B6E4F", "#6A1B9A", "#8B5A00",
        "#005F73", "#7A0019", "#3D348B", "#2A9D8F", "#4A4A4A"
    )
    rep(base, length.out = max(1, as.integer(n)))
}

make_afc_graph <- function(toplot, classes, clnb, xlab, ylab, cex.txt = NULL, leg = FALSE, cmd = FALSE, black = FALSE, xminmax=NULL, yminmax=NULL, color=NULL) {
    
    rain <- rainbow(clnb)
    compt <- 1
    tochange <- NULL
    #for (my.color in rain) {
    #    my.color <- col2rgb(my.color)
    #    if ((my.color[1] > 200) & (my.color[2] > 200) & (my.color[3] < 20)) {
    #       tochange <- append(tochange, compt)   
    #    }
    #    compt <- compt + 1
    #}
    #if (!is.null(tochange)) {
    #    gr.col <- grey.colors(length(tochange))
    #    compt <- 1
    #    for (val in tochange) {
    #        rain[val] <- gr.col[compt]
    #        compt <- compt + 1
    #    }
    #}
	rain <- del.yellow(rain)
    cl.color <- rain[classes]
    if (black) {
        cl.color <- 'black'
    }
    if (!is.null(color)) {
        cl.color <- color
    }
	plot(toplot[,1],toplot[,2], pch='', xlab = xlab, ylab = ylab, xlim=xminmax, ylim = yminmax)
	abline(h=0, v=0, lty = 'dashed')
	if (is.null(cex.txt))
		text(toplot[,1],toplot[,2],rownames(toplot),col=cl.color, offset=0)
	else 
		#require(wordcloud)
		#textplot(toplot[,1],toplot[,2],rownames(toplot),col=cl.color, cex = cex.txt, xlim=xminmax, ylim = yminmax)
        text(toplot[,1],toplot[,2],rownames(toplot),col=cl.color, cex = cex.txt, offset=0)

    if (!cmd) {    
	    dev.off()
    }
}

plot.dendro.prof <- function(tree, classes, chisqtable, nbbycl = 60, type.dendro = "phylogram", from.cmd = FALSE, bw = FALSE, lab = NULL) {
    library(ape)
    library(wordcloud)
    classes<-classes[classes!=0]
	classes<-as.factor(classes)
	sum.cl<-as.matrix(summary(classes, maxsum=1000000))
	sum.cl<-(sum.cl/colSums(sum.cl)*100)
	sum.cl<-round(sum.cl,2)
	sum.cl<-cbind(sum.cl,as.matrix(100-sum.cl[,1]))
    sum.cl <- sum.cl[,1]
    tree.order<- as.numeric(tree$tip.label)
	vec.mat<-NULL
    row.keep <- select.chi.classe(chisqtable, nbbycl)
    #et.keep <- select.chi.classe.et(chisqtable, 10)
    #print(chistable[et.keep,])
    toplot <- chisqtable[row.keep,]
    lclasses <- list()
    for (classe in 1:length(sum.cl)) {
       ntoplot <- toplot[,classe]
       names(ntoplot) <- rownames(toplot)
       ntoplot <- ntoplot[order(ntoplot, decreasing = TRUE)]
       ntoplot <- round(ntoplot, 0)
       if (length(toplot) > nbbycl) {
           ntoplot <- ntoplot[1:nbbycl]
       }       
       ntoplot <- ntoplot[which(ntoplot > 0)]
       #ntoplot <- ntoplot[order(ntoplot)]
       #ntoplot <- ifelse(length(ntoplot) > nbbycl, ntoplot[1:nbbycl], ntoplot)
       lclasses[[classe]] <- ntoplot
    }
    vec.mat <- matrix(1, nrow = 3, ncol = length(sum.cl))
	vec.mat[2,] <- 2
    vec.mat[3,] <- 3:(length(sum.cl)+2)
    layout(matrix(vec.mat, nrow=3, ncol=length(sum.cl)),heights=c(2,1,6))
    if (! bw) {
        class.cols <- safe.class.palette(length(sum.cl))
        col <- class.cols[as.numeric(tree$tip.label)]
        colcloud <- class.cols
    } else {
        col <- rep('black', length(sum.cl))[as.numeric(tree$tip.label)]
        colcloud <- rep('grey35', length(sum.cl))
    }
	label.ori<-tree$tip.label
    if (!is.null(lab)) {
        tree$tip.label <- lab
    } else {
	    tree$tip.label<-paste('classe ',tree$tip.label)
	}
	par(mar=c(2,1,0,1))
	plot.phylo(
	    tree,
	    label.offset=0.1,
	    tip.col=col,
	    type=type.dendro,
	    direction='downwards',
	    srt=90,
	    adj=0.5,
	    cex=1.55,
	    font=2,
	    edge.width=1.4,
	    y.lim=c(-0.3,tree$Nnode)
	)
	par(mar=c(0,0,0,0))
	d <- barplot(-sum.cl[tree.order], col=col, names.arg='', axes=FALSE, axisname=FALSE)
	text(x=d, y=(-sum.cl[tree.order]+3), label=paste(round(sum.cl[tree.order],1),'%'), cex=1.1, font=2)
    for (i in tree.order) {
        par(mar=c(0,0,1,0),cex=0.7)
        #wordcloud(names(lclasses[[i]]), lclasses[[i]], scale = c(1.5, 0.2), random.order=FALSE, colors = colcloud[i])
        yval <- 1.1
        plot(0,0,pch='', axes = FALSE)
        if (length(lclasses[[i]]) == 0) {
            next
        }
        vcex <- norm.vec(lclasses[[i]], 2, 3)
        for (j in 1:length(lclasses[[i]])) {
            yval <- yval-(strheight( names(lclasses[[i]])[j],cex=vcex[j])+0.02)
            text(-0.9, yval, names(lclasses[[i]])[j], cex = vcex[j], col = colcloud[i], adj=0)
        }
    }
    if (!from.cmd) {
        dev.off()
    }
    
}

plot.dendro.cloud <- function(tree, classes, chisqtable, nbbycl = 60, type.dendro = "phylogram", from.cmd = FALSE, bw = FALSE, lab = NULL) {
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
    row.keep <- select.chi.classe(chisqtable, nbbycl)
    toplot <- chisqtable[row.keep,]
    lclasses <- list()
    for (classe in 1:length(sum.cl)) {
       ntoplot <- toplot[,classe]
       names(ntoplot) <- rownames(toplot)
       ntoplot <- ntoplot[order(ntoplot, decreasing = TRUE)]
       ntoplot <- round(ntoplot, 0)
       if (length(toplot) > nbbycl) {
            ntoplot <- ntoplot[1:nbbycl]
       }
       ntoplot <- ntoplot[order(ntoplot)]
       ntoplot <- ntoplot[which(ntoplot > 0)]
       #ntoplot <- ifelse(length(ntoplot) > nbbycl, ntoplot[1:nbbycl], ntoplot)
       lclasses[[classe]] <- ntoplot
    }
	for (i in 1:length(sum.cl)) vec.mat<-append(vec.mat,1)
	v<-2
	for (i in 1:length(sum.cl)) {
		vec.mat<-append(vec.mat,v)
		v<-v+1
	}    
    layout(matrix(vec.mat,length(sum.cl),2),widths=c(1,2))
    if (! bw) {
        class.cols <- safe.class.palette(length(sum.cl))
        col <- class.cols[as.numeric(tree$tip.label)]
        colcloud <- class.cols
    } else {
        col <- rep('black', length(sum.cl))[as.numeric(tree$tip.label)]
        colcloud <- rep('grey35', length(sum.cl))
    }
    par(mar=c(0,0,0,0))
	label.ori<-tree$tip.label
    if (!is.null(lab)) {
        tree$tip.label <- lab
    } else {
	    tree$tip.label<-paste('classe ',tree$tip.label)
	}
	plot.phylo(tree,label.offset=0.25,tip.col=col, type=type.dendro, cex=1.2, font=2, edge.width=1.4)
    for (i in rev(tree.order)) {
        par(mar=c(0,0,1,0),cex=0.9)
        if (length(lclasses[[i]]) > 0) {
            wordcloud(names(lclasses[[i]]), lclasses[[i]], scale = c(2.5, 0.5), random.order=FALSE, colors = colcloud[i])
        } else {
            plot.new()
            text(0.5, 0.5, 'sem termos', cex = 1)
        }
    }
}

plot.dendropr <- function(tree, classes, type.dendro="phylogram", histo=FALSE, from.cmd=FALSE, bw=FALSE, lab = NULL, tclasse=TRUE) {
	classes<-classes[classes!=0]
	classes<-as.factor(classes)
	sum.cl<-as.matrix(summary(classes, maxsum=1000000))
	sum.cl<-(sum.cl/colSums(sum.cl)*100)
	sum.cl<-round(sum.cl,2)
	sum.cl<-cbind(sum.cl,as.matrix(100-sum.cl[,1]))
    tree.order<- as.numeric(tree$tip.label)


    if (! bw) {
        class.cols <- safe.class.palette(nrow(sum.cl))
        col <- class.cols[as.numeric(tree$tip.label)]
        col.bars <- col
        col.pie <- class.cols
    } else {
        col = 'black'
        col.bars = 'grey'
        col.pie <- rep('grey',nrow(sum.cl))
    }
	vec.mat<-NULL
	for (i in 1:nrow(sum.cl)) vec.mat<-append(vec.mat,1)
	v<-2
	for (i in 1:nrow(sum.cl)) {
		vec.mat<-append(vec.mat,v)
		v<-v+1
	}
	par(mar=c(0,0,0,0))
    if (tclasse) {
        if (! histo) {
	        layout(matrix(vec.mat,nrow(sum.cl),2),widths=c(3,1))
        } else {
            layout(matrix(c(1,2),1,byrow=TRUE), widths=c(3,2),TRUE)
        }
    }
	par(mar=c(0,0,0,0),cex=1)
	label.ori<-tree$tip.label
    if (!is.null(lab)) {
        tree$tip.label <- lab
    } else {
	    tree$tip.label<-paste('classe ',tree$tip.label)
    }
	plot.phylo(
	    tree,
	    label.offset=0.1,
	    tip.col=col,
	    type=type.dendro,
	    cex=1.2,
	    font=2,
	    edge.width=1.4
	)
    #cl.order <- as.numeric(label.ori)
    #sum.cl[cl.order,1]
	#for (i in 1:nrow(sum.cl)) {
    if (tclasse) {
        if (! histo) {
    	    for (i in rev(tree.order)) {
                par(mar=c(0,0,1,0),cex=0.7)
    		    pie(sum.cl[i,],col=c(col.pie[i],'white'),radius = 1, labels='', clockwise=TRUE, main = paste('classe ',i,' - ',sum.cl[i,1],'%' ))
    	    }
        } else {
            par(cex=1.2)
            par(mar=c(2,0,1,1))
            to.plot <- sum.cl[tree.order,1]
            d <- barplot(to.plot,horiz=TRUE, col=col.bars, names.arg='', axes=FALSE, axisname=FALSE)
            text(x=to.plot, y=d[,1], label=paste(round(to.plot,1),'%'), adj=c(1.1, 0.5), cex=1.5, font=2)
        }
    }
    mtext("dendrograma a partir do chd1", side=1, line=0.8, cex=1.1, font=2)
    if (!from.cmd) dev.off()
	tree[[2]]<-label.ori
}
#tree <- tree.cut1$tree.cl
#to.plot <- di
plot.dendro.lex <- function(tree, to.plot, bw=FALSE, lab=NULL, lay.width=c(3,3,2), colbar=NULL, classes=NULL, direction = 'rightwards', cmd=FALSE) {
    tree.order<- as.numeric(tree$tip.label)
	if (!is.null(classes)) {
		classes<-classes[classes!=0]
		classes<-as.factor(classes)
		sum.cl<-as.matrix(summary(classes, maxsum=1000000))
		sum.cl<-(sum.cl/colSums(sum.cl)*100)
		sum.cl<-round(sum.cl,2)
		sum.cl<-cbind(sum.cl,as.matrix(100-sum.cl[,1]))
	}
    par(mar=c(0,0,0,0))
    if (direction == 'rightwards') {
        srt <- 0
        adj <- NULL
        horiz <- TRUE
	    if (!is.null(classes)) {
		    matlay <- matrix(c(1,2,3,4),1,byrow=TRUE)
		    lay.width <- c(3,2,3,2)
	    } else {
		    matlay <- matrix(c(1,2,3),1,byrow=TRUE)
	    }
    } else {
        srt <- 90
        adj <- 0.5
        horiz <- FALSE
        if (!is.null(classes)) {
            matlay <- matrix(c(1,2,3,4,4,4),3)
        } else {
            matlay <- matrix(c(1,2,3,3),2)
        }
        lay.width <- c(5,2)
    }
    layout(matlay, widths=lay.width,TRUE)
	par(mar=c(3,0,2,4),cex=1)
	label.ori<-tree$tip.label
    if (!is.null(lab)) {
        tree$tip.label <- lab
    } else {
	    tree$tip.label<-paste('classe ',tree$tip.label)
    }
    to.plot <- matrix(to.plot[,tree.order], nrow=nrow(to.plot), dimnames=list(rownames(to.plot), colnames(to.plot)))
    if (!bw) {
		col <- rainbow(ncol(to.plot))
		col <- del.yellow(col)
		if (is.null(colbar)) {
	        col.bars <- rainbow(nrow(to.plot))
	        col.bars <- del.yellow(col.bars)
		} else {
			col.bars <- colbar
		}
    } else {
        col <- 'black'
        col.bars <- grey.colors(nrow(to.plot),0,0.8)
    }
    col <- col[tree.order]
	plot.phylo(tree,label.offset=0.2,tip.col=col, direction = direction, srt=srt, adj = 0.5, edge.width = 2)
	if (!is.null(classes)) {
		par(cex=1.2)
		par(mar=c(3,0,2,1))
		to.plota <- sum.cl[tree.order,1]
		d <- barplot(to.plota,horiz=TRUE, col=col, names.arg='', axes=FALSE, axisname=FALSE)
		text(x=to.plota, y=d[,1], label=paste(round(to.plota,1),'%'), adj=c(1.1, 0.5), cex=1.5)
	}
    par(mar=c(3,0,2,1))
    d <- barplot(to.plot,horiz=horiz, col=col.bars, beside=TRUE, names.arg='', space = c(0.1,0.6), axisname=FALSE)
    c <- colMeans(d)
    c1 <- c[-1]
    c2 <- c[-length(c)]
    cc <- cbind(c1,c2)
    lcoord <- apply(cc, 1, mean)
    abline(h=lcoord)
    if (min(to.plot) < 0) {
        amp <- abs(max(to.plot) - min(to.plot))
    } else {
        amp <- max(to.plot)
    }
    if (amp < 10) {
        d <- 2
    } else {
        d <- signif(amp%/%10,1)
    }
    mn <- round(min(to.plot))
    mx <- round(max(to.plot))
    for (i in mn:mx) {
        if ((i/d) == (i%/%d)) { 
            abline(v=i,lty=3)
        }
    }    
    par(mar=c(0,0,0,0))
    plot(0, axes = FALSE, pch = '')
    legend(x = 'center' , rev(rownames(to.plot)), fill = rev(col.bars))
    if (!cmd) {
        dev.off()
    }
	tree[[2]]<-label.ori
}

plot.spec <- function(spec, nb.word = 20) {
	word.to.plot <- NULL
	word.size <- NULL
	rno <- rownames(spec)
	cn <- colnames(spec)
	if (nb.word > length(rno)) {nb.word <- length(rno)}
	for (val in 1:ncol(spec)) {
		rn <- rno[order(spec[,val], decreasing=T)][1:nb.word]
		score <- spec[order(spec[,val], decreasing=T),val][1:nb.word]
		word.to.plot <- cbind(word.to.plot, rn)
		word.size <- cbind(word.size, score)
	}
	mat.lay <- matrix(1:ncol(spec),nrow=1,ncol=ncol(spec))
	layout(mat.lay)
	for (i in 1:ncol(spec)) {
		col <- ifelse((i %% 2) == 0, 'red', 'blue')
		par(mar=c(0,0,1,0),cex=0.7)
	    yval <- 1.1
	    plot(0,0,pch='', axes = FALSE)
	    vcex <- norm.vec(word.size[,i], 2, 3)
		text(-0.9, -0.5, cn[i], cex = 1, adj=0, srt=90, col='black')
	    for (j in 1:length(word.size[,i])) {
	        yval <- yval-(strheight(word.to.plot[j,i],cex=vcex[j])+0.02)
	        text(-0.9, yval, word.to.plot[j,i], cex = vcex[j], col = col, adj=0)
	    }
	}


}

plot.alceste.graph <- function(rdata,nd=3,layout='fruke', chilim = 2) {
    load(rdata)
    if (is.null(debsup)) {
        tab.toplot<-afctable[1:(debet+1),]
        chitab<-chistabletot[1:(debet+1),]
    } else {
        tab.toplot<-afctable[1:(debsup+1),]
        chitab<-chistabletot[1:(debsup+1),]
    }
    rkeep<-select_point_chi(chitab,chilim)
    tab.toplot<-tab.toplot[rkeep,]
    chitab<-chitab[rkeep,]
    dm<-dist(tab.toplot,diag=TRUE,upper=TRUE)
    cn<-rownames(tab.toplot)
    cl.toplot<-apply(chitab,1,which.max)
    col<-rainbow(ncol(tab.toplot))[cl.toplot]
    library(igraph)
    g1 <- graph.adjacency(as.matrix(dm), mode = 'lower', weighted = TRUE)
    g.max<-minimum.spanning.tree(g1)
    we<-(rowSums(tab.toplot)/max(rowSums(tab.toplot)))*2
    #lo <- layout.fruchterman.reingold(g.max,dim=nd)
    lo<- layout.kamada.kawai(g.max,dim=nd)
    print(nrow(tab.toplot))
    print(nrow(chitab))
    print(length(we))
    print(length(col))
    print(length(cn))
    if (nd == 3) {
        rglplot(g.max, vertex.label = cn, vertex.size = we*3, edge.width = 0.5, edge.color='black', vertex.label.color = col,vertex.color = col, layout = lo, vertex.label.cex = 1)
    } else if (nd == 2) {
        plot(g.max, vertex.label = cn, vertex.size = we, edge.width = 0.5, edge.color='black', vertex.label.color = col,vertex.color = col, layout = lo, vertex.label.cex = 0.8)
    }

}

make.simi.afc <- function(x,chitable,lim=0, alpha = 0.1, movie = NULL) {
    library(igraph)
    chimax<-as.matrix(apply(chitable,1,max))
    chimax<-as.matrix(chimax[,1][1:nrow(x)])
    chimax<-cbind(chimax,1:nrow(x))
    order_chi<-as.matrix(chimax[order(chimax[,1],decreasing = TRUE),])
    if ((lim == 0) || (lim>nrow(x))) lim <- nrow(x)
    x<-x[order_chi[,2][1:lim],]
    maxchi <- chimax[order_chi[,2][1:lim],1]
    #-------------------------------------------------------
    limit<-nrow(x)
    distm<-dist(x,diag=TRUE)
    distm<-as.matrix(distm)
    g1<-graph.adjacency(distm,mode='lower',weighted=TRUE)
    g1<-minimum.spanning.tree(g1)
    lo<-layout.kamada.kawai(g1,dim=3)
    lo <- layout.norm(lo, -3, 3, -3, 3, -3, 3)
    mc<-rainbow(ncol(chistabletot))
    chitable<-chitable[order_chi[,2][1:lim],]
    cc <- apply(chitable, 1, which.max)
    cc<-mc[cc]
    #mass<-(rowSums(x)/max(rowSums(x))) * 5
    maxchi<-norm.vec(maxchi, 0.03, 0.3)
    rglplot(g1,vertex.label = vire.nonascii(rownames(x)),vertex.label.color= cc,vertex.label.cex = maxchi, vertex.size = 0.1, layout=lo, rescale=FALSE)
    text3d(lo[,1], lo[,2],lo[,3], rownames(x), cex=maxchi, col=cc)
    #rgl.spheres(lo, col = cc, radius = maxchi, alpha = alpha)
    rgl.bg(color = c('white','black'))
    if (!is.null(movie)) {
        require(tcltk)
        ReturnVal <- tkmessageBox(title="RGL 3 D",message="Cliquez pour commencer le film",icon="info",type="ok")

        movie3d(spin3d(axis=c(0,1,0),rpm=6), movie = 'film_graph', frames = "tmpfilm", duration=10, clean=TRUE, top = TRUE, dir = movie)
        ReturnVal <- tkmessageBox(title="RGL 3 D",message="Film fini !",icon="info",type="ok")
    }
	while (rgl.cur() != 0)
		Sys.sleep(1)

}

# from igraph
norm.vec <- function(v, min, max) {

  vr <- range(v)
  if (vr[1]==vr[2]) {
    fac <- 1
  } else {
    fac <- (max-min)/(vr[2]-vr[1])
  }
  (v-vr[1]) * fac + min
}


vire.nonascii <- function(rnames) {
    print('vire non ascii')
    couple <- list(c('é','e'),
                c('è','e'),
                c('ê','e'),
                c('ë','e'),
                c('î','i'),
                c('ï','i'),
                c('ì','i'),
                c('à','a'),
                c('â','a'),
                c('ä','a'),
                c('á','a'),
                c('ù','u'),
                c('û','u'),
                c('ü','u'),
                c('ç','c'),
                c('ò','o'),
                c('ô','o'),
                c('ö','o'),
                c('ñ','n')
                )

    for (c in couple) {
        rnames<-gsub(c[1],c[2], rnames)
    }
    rnames
}



#par(mar=c(0,0,0,0))
#layout(matrix(c(1,2),1,byrow=TRUE), widths=c(3,2),TRUE)
#par(mar=c(1,0,1,0), cex=1)
#plot.phylo(tree,label.offset=0.1)
#par(mar=c(0,0,0,1))
#to.plot <- sum.cl[cl.order,1]
#d <- barplot(to.plot,horiz=TRUE, names.arg='', axes=FALSE, axisname=FALSE)
#text(x=to.plot, y=d[,1], label=round(to.plot,1), adj=1.2)

make.afc.attributes <- function(rn, afc.table, contafc, clnb, column = FALSE, x=1, y=2) {
    if (!column){
        nd <- clnb - 1
        afc.res <- afc.table$ligne
        #tokeep <- which(row.names(afc.res) %in% rn)
        afc.res <- afc.res[rn,]
        debcor <- (nd*2) + 1
        cor <- afc.res[,debcor:(debcor+nd-1)][,c(x,y)]
        debctr <- (nd*3) + 1
        ctr <- afc.res[,debctr:(debctr+nd-1)][,c(x,y)]
        massdeb <- (nd*4) + 1
        mass <- afc.res[,massdeb]
        chideb <- massdeb + 1
        chi <- afc.res[,chideb]
        inertiadeb <- chideb + 1
        inertia <- afc.res[,inertiadeb]
        frequence <- rowSums(contafc[rn,])
    }
    res <- list(frequence=frequence, cor, ctr, mass = mass, chi=chi, inertia=inertia)
    return(res)
}


afctogexf <- function(fileout, toplot, classes, clnb, sizes, nodes.attr=NULL) {
    toplot <- toplot[,1:3]
    toplot[,3] <- 0
    #toplot <- afc$rowcoord[1:100,1:3]
    #toplot[,3] <- 0
    #rownames(toplot)<-afc$rownames[1:100]
    cc <- rainbow(clnb)[classes]
    cc <- t(sapply(cc, col2rgb, alpha=TRUE))
    #sizes <- apply(chistabletot[1:100,], 1, max)
    
    nodes <- data.frame(cbind(1:nrow(toplot), rownames(toplot)))
    colnames(nodes) <- c('id', 'label')
    nodes[,1] <- as.character(nodes[,1])
    nodes[,2] <- as.character(nodes[,2])
    #nodes attributs
    if (! is.null(nodes.attr)) {
        nodesatt <- as.data.frame(nodes.attr)
    } else {
        nodesatt <- data.frame(cbind(toplot[,1],toplot[,2]))
    }
    #make axes
    edges<-matrix(c(1,1),ncol=2)
    xmin <- min(toplot[,1])
    xmax <- max(toplot[,1])
    ymin <- min(toplot[,2])
    ymax <- max(toplot[,2])
    nodes<-rbind(nodes, c(nrow(nodes)+1, 'F1'))
    nodes<-rbind(nodes, c(nrow(nodes)+1, 'F1'))
    nodes<-rbind(nodes, c(nrow(nodes)+1, 'F2'))
    nodes<-rbind(nodes, c(nrow(nodes)+1, 'F2'))
    nodesatt<-rbind(nodesatt, c(0,0))
    nodesatt<-rbind(nodesatt, c(0,0))
    nodesatt<-rbind(nodesatt, c(0,0))
    nodesatt<-rbind(nodesatt, c(0,0))
    toplot <- rbind(toplot, c(xmin, 0,0))
    toplot <- rbind(toplot, c(xmax,0,0))
    toplot <- rbind(toplot, c(0,ymin,0))
    toplot <- rbind(toplot, c(0,ymax,0))
    cc <- rbind(cc, c(255,255,255,1))
    cc <- rbind(cc, c(255,255,255,1))
    cc <- rbind(cc, c(255,255,255,1))
    cc <- rbind(cc, c(255,255,255,1))
    sizes <- c(sizes, c(0.5, 0.5, 0.5, 0.5))
    edges <- rbind(edges, c(nrow(nodes)-3, nrow(nodes)-2))
    edges <- rbind(edges, c(nrow(nodes)-1, nrow(nodes)))
    write.gexf(nodes, edges, output=fileout, nodesAtt=nodesatt, nodesVizAtt=list(color=cc, position=toplot, size=sizes))
}

simi.to.gexf <- function(fileout, graph.simi, nodes.attr = NULL) {
	lo <- graph.simi$layout
	if (ncol(lo) == 3) {
		lo[,3] <- 0
	} else {
		lo <- cbind(lo, rep(0,nrow(lo)))
	}
	g <- graph.simi$graph
	nodes <- data.frame(cbind(1:nrow(lo), V(g)$name))
	colnames(nodes) <- c('id', 'label')
	if (! is.null(nodes.attr)) {
		nodesatt <- as.data.frame(nodes.attr)
	} else {
		nodesatt <- data.frame(cbind(lo[,1],lo[,2]))
	}
	edges <- as.data.frame(get.edges(g, c(1:ecount(g))))
	col <- graph.simi$color
	col <- t(sapply(col, col2rgb, alpha=TRUE))
	write.gexf(nodes, edges, output=fileout, nodesAtt=nodesatt, nodesVizAtt=list(color=col,position=lo, size=graph.simi$label.cex), edgesVizAtt=list(size=graph.simi$we.width))
}

graphml.to.file <- function(graph.path) {
    library(igraph)
    g <- read.graph(graph.path, format='graphml')
    layout <- layout.fruchterman.reingold(g, dim=3)
    #print(V(g)$color)
    graph.simi <- list(graph=g, layout=layout, color = V(g)$color ,eff=V(g)$weight)
    graph.simi
}



graph.to.file <- function(graph.simi, nodesfile = NULL, edgesfile = NULL, community = FALSE, color = NULL, sweight = NULL) {
	require(igraph)
	g <- graph.simi$graph
    print(graph.simi$eff)
    if (!is.null(graph.simi$eff)) {
	    V(g)$weight <- graph.simi$eff
    } else {
        V(g)$weight <- graph.simi$label.cex
    }
	layout <- layout.norm(graph.simi$layout,-5,5,-5,5,-5,5)
	print(layout)
	V(g)$x <- layout[,1]
	V(g)$y <- layout[,2]
	if (ncol(layout) == 3) {
		V(g)$z <- layout[,3]
	}
	if (community) {
		member <- graph.simi$communities$membership
		col <- rainbow(max(member))
		v.colors <- col[member]
		v.colors <- col2rgb(v.colors)
		V(g)$r <- v.colors[1,]
		V(g)$g <- v.colors[2,]
		V(g)$b <- v.colors[3,]
	}
	if (!is.null(color)) {
		v.colors <- col2rgb(color)
		V(g)$r <- v.colors[1,]
		V(g)$g <- v.colors[2,]
		V(g)$b <- v.colors[3,]		
	}
	if (!is.null(sweight)) {
		V(g)$sweight <- sweight
	}
	df <- get.data.frame(g, what='both')
	if (!is.null(nodesfile)) {
		write.table(df$vertices, nodesfile, sep='\t', row.names=FALSE)
	}
	if (!is.null(edgesfile)) {
		write.table(df$edges, edgesfile, sep='\t', row.names=FALSE)
	}
	if (is.null(edgesfile) & is.null(nodesfile)) {
		df
	}
}

graph.to.file2 <- function(graph, layout, nodesfile = NULL, edgesfile = NULL, community = FALSE, color = NULL, sweight = NULL) {
	require(igraph)
	g <- graph
	V(g)$x <- layout[,1]
	V(g)$y <- layout[,2]
	if (ncol(layout) == 3) {
		V(g)$z <- layout[,3]
	}
	v.colors <- col2rgb(V(g)$color)
	V(g)$r <- v.colors[1,]
	V(g)$g <- v.colors[2,]
	V(g)$b <- v.colors[3,]		
	
	if (!is.null(sweight)) {
		V(g)$sweight <- sweight
	}
	if (is.null(V(g)$weight)) {
		if (!is.null(sweight)) {
			V(g)$weight <- sweight
		} else {
			V(g)$weight <- 1
		}
	}
	df <- get.data.frame(g, what='both')
	if (!is.null(nodesfile)) {
		write.table(df$vertices, nodesfile, sep='\t', row.names=FALSE)
	}
	if (!is.null(edgesfile)) {
		write.table(df$edges, edgesfile, sep='\t', row.names=FALSE)
	}
	if (is.null(edgesfile) & is.null(nodesfile)) {
		df
	}
}


dist2list <- function(mat, outfile = NULL) {
	m <- as.matrix(mat)
	xy <- t(combn(colnames(m), 2))
	m <- data.frame(xy, dist=m[xy])
	if (!is.null(outfile)) {
		write.csv2(m, file=outfile)
	} else {
		m
	}
}
