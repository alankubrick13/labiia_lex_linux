#Author: Pierre Ratinaud
#Copyright (c) 2008-2020 Pierre Ratinaud
#License: GNU/GPL


#fichier genere par IRaMuTeq
source('%s', encoding = 'utf8')
typegraph <- %i
edgesfile <- "%s"
nodesfile <- "%s"
what <- %i
x <- %i
y <- %i
z <- %i
qui <- %i
over <- %s
do.select.nb <- %s
select.nb <- %i
do.select.chi <- %s
select.chi <- %i
do.select.chi.classe <- %s
ptbycluster <- %i
cex.txt <- %s
txt.min <- %i
txt.max <- %i
fileout <- "%s"
width <- %i
height <- %i
taillecar <- %i
alpha <- %i/100
dofilm <- %s
tchi <- %s
tchi.min <- %i
tchi.max <- %i
dirout <- "%s"
do.svg <- %s
xminmax <- NULL
yminmax <- NULL

xlab <- paste('fator ', x, ' -')
ylab <- paste('fator ', y, ' -')
if (!typegraph == 0) {zlab <- paste('fator ', z, ' -')}
xlab <- paste(xlab,round(afc_table$facteur[x,2],2),sep = ' ')
xlab <- paste(xlab,' %%',sep = '')
ylab <- paste(ylab,round(afc_table$facteur[y,2],2),sep = ' ')
ylab <- paste(ylab,' %%',sep = '')
if (!typegraph == 0) {
    zlab <- paste(zlab,round(afc_table$facteur[z,2],2),sep = ' ')
    zlab <- paste(zlab,' %%',sep = '')
}

if ( qui == 3 ) {
    if ( what == 0 ) table.in <- afc$colcoord
    if ( what == 1 ) table.in <- afc$colcrl
    rownames(table.in) <- afc$colnames
    eff <- afc$colmass
    if (typegraph == 0) {
        table.in<-table.in[,c(x,y)]
    } else {
        table.in<-table.in[,c(x,y,z)]
        rx <- range(table.in[,1], na.rm = TRUE)
        ry <- range(table.in[,2], na.rm = TRUE)
        rz <- range(table.in[,3], na.rm = TRUE)
    }
    classes <- c(1:clnb)
    maxchi <- 1
    cex.par <- rep(taillecar/10, nrow(table.in))
} else {
    if ( what == 0 ) table.in <- afc$rowcoord
    if ( what == 1 ) table.in <- afc$rowcrl
    rownames(table.in) <- afc$rownames
    tablechi <- chistabletot
    rn.keep <- c()
    if (typegraph == 0) {
        table.in<-table.in[,c(x,y)]
    } else {
        table.in<-table.in[,c(x,y,z)]
        rx <- range(table.in[,1], na.rm = TRUE)
        ry <- range(table.in[,2], na.rm = TRUE)
        rz <- range(table.in[,3], na.rm = TRUE)
    }
    if (exists('afctable')) {
        eff <- rowSums(afctable)
    } else {
        eff <- afc$rowmass
    }

    if (!is.null(debsup)) {
        if ( qui == 0 ) {
           table.in <- table.in[1:(debsup-1),]
           tablechi <- tablechi[1:(debsup-1),]
           cex.par <- eff[1:(debsup-1)]
        }
        if ( qui == 1 ) {
           table.in <- table.in[debsup:(debet-1),] 
           tablechi <- tablechi[debsup:(debet-1),]
           cex.par <- eff[debsup:(debet-1)]
        }
        if ( qui == 2 ) {
           fin <- nrow(table.in)
           table.in <- table.in[debet:nrow(table.in),] 
           tablechi <- tablechi[debet:nrow(tablechi),]
           cex.par <- eff[debet:fin]
        }
    }
    
    if (is.null(debsup)) {
        if (qui == 0) {
            if (!is.null(debet)) {
                table.in <- table.in[1:(debet-1),] 
                tablechi <- tablechi[1:(debet-1),]
                cex.par <- eff[1:(debet-1)]
            } else {
                cex.par <- eff
            }
        } else {
            fin <- nrow(table.in)
            table.in <- table.in[debet:nrow(table.in),]
            tablechi <- tablechi[debet:nrow(tablechi),]
            cex.par <- eff[debet:fin]
        }
    }
        
    if (do.select.nb) {
        if (select.nb > nrow(table.in)) select.nb <- nrow(table.in)
        row.keep <- select_point_nb(tablechi, select.nb)
        table.in <- table.in[row.keep,]
        tablechi <- tablechi[row.keep,]
    } else if (do.select.chi) {
        if (select.chi > max(tablechi)) select.chi <- max(tablechi)
        row.keep <- select_point_chi(tablechi, select.chi)
        table.in <- table.in[row.keep,]
        tablechi <- tablechi[row.keep,]
    } else if (do.select.chi.classe) {
        row.keep <- select.chi.classe(tablechi, ptbycluster, active=FALSE)
        table.in <- table.in[row.keep,]
        tablechi <- tablechi[row.keep,]        
    } else {
        row.keep <- 1:nrow(table.in)
    }
    classes <- apply(tablechi, 1, which.max)
    maxchi <- apply(tablechi, 1, max)
    infp <-  which(is.infinite(maxchi) & maxchi > 0)
    if (length(infp)) {
        maxchi[infp] <- NA
        if (!length(infp) == length(maxchi)) {
            valmax <- max(maxchi, na.rm = TRUE)
        } else {
            valmax <- 8
        }
        maxchi[infp] <- valmax + 2
    } 
    if (cex.txt) {
        #row.keep <- append(row.keep, rn.keep)
        #row.keep <- unique(row.keep)
        cex.par <- cex.par[row.keep]
        cex.par <- norm.vec(cex.par, txt.min/10, txt.max/10)
    } else if (tchi) {
        cex.par <- maxchi
        cex.par <- norm.vec(cex.par, tchi.min/10, tchi.max/10)
    } else {
        cex.par <- rep(taillecar/10, nrow(table.in))
    }
}

if (is.null(xminmax)) {
        xminmax <- c(min(table.in[,1], na.rm = TRUE) + ((max(cex.par)/10) * min(table.in[,1], na.rm = TRUE)), max(table.in[,1], na.rm = TRUE) + ((max(cex.par)/10) * max(table.in[,1], na.rm = TRUE)))
    }
    if (is.null(yminmax)) {
        yminmax <- c(min(table.in[,2], na.rm = TRUE) + ((max(cex.par)/10) * min(table.in[,2], na.rm = TRUE)), max(table.in[,2], na.rm = TRUE) + ((max(cex.par)/10) * max(table.in[,2], na.rm = TRUE)))
    }

if (typegraph == 0 || typegraph == 2) {

    open_file_graph(fileout, width = width, height = height, svg = do.svg)
    parcex <- taillecar/10
    par(cex = parcex)
    if (over) {
        table.in <- table.in[order(cex.par, decreasing = TRUE),]
        classes <- classes[order(cex.par, decreasing = TRUE)]
        cex.par <- cex.par[order(cex.par, decreasing = TRUE)]
        table.out <- stopoverlap(table.in, cex.par=cex.par, xlim = xminmax, ylim = yminmax)
        table.in <- table.out$toplot
        notplot <- table.out$notplot
        if (! is.null(notplot)) {
            write.csv2(notplot, file = paste(fileout,'_notplotted.csv', sep=''))
        }    
        classes <- classes[table.in[,4]]
        cex.par <- cex.par[table.in[,4]]
    }
    if (typegraph == 0) {
        make_afc_graph(table.in, classes, clnb, xlab, ylab, cex.txt = cex.par, xminmax = xminmax, yminmax = yminmax)
    } else {
        dev.off()
        require(rgexf)
        nodes.attr <- make.afc.attributes(rownames(table.in), afc_table, afctable, clnb)
        if (qui != 3) {
            tokeep <- rownames(chistabletot) %%in%% rownames(table.in)
            chis <- chistabletot[tokeep,]
            chis<-chis[rownames(table.in),]
            nodes.attr$chiclasse <- chis
        } else {
            chis <- NULL
        }
        afctogexf(fileout, table.in, classes, clnb, cex.par, nodes.attr = nodes.attr)
    }

} else {
	if (typegraph == 4) {
		library(igraph)
		rain = rainbow(clnb)
	    col = rain[classes]
		g <- make_empty_graph()
		vertex <- rownames(table.in)
		g <- add.vertices(g, length(vertex), attr=list(weight=cex.par, names=vertex, color=col))
		minx <- min(table.in[,1])
		maxx <- max(table.in[,1])
		miny <- min(table.in[,2])
		maxy <- max(table.in[,2])
		minz <- min(table.in[,3])
		maxz <- max(table.in[,3])
		table.in <- rbind(table.in, c(minx, 0, 0))
		rminx <- nrow(table.in)
		table.in <- rbind(table.in, c(maxx, 0, 0))
		rmaxx <- nrow(table.in)
		table.in <- rbind(table.in, c(0, miny, 0))
		rminy <- nrow(table.in)
		table.in <- rbind(table.in, c(0, maxy, 0))
		rmaxy <- nrow(table.in)
		table.in <- rbind(table.in, c(0, 0, minz))
		rminz <- nrow(table.in)
		table.in <- rbind(table.in, c(0, 0, maxz))
		rmaxz <- nrow(table.in)
		g <- add.vertices(g, 6, attr=list(weight=c(0.1,0.1,0.1,0.1,0.1,0.1), names=c(rminx,rmaxx,rminy,rmaxy,rminz,rmaxz), color=c('white','white','white','white','white','white')))
		g <- g + edge(rminx, rmaxx, weight=0.1) + edge(rminy, rmaxy, weight=0.1) + edge(rminz, rmaxz, weight=0.1)
		table.in <- layout.norm(table.in, -5,5,-5,5,-5,5)
		graph.to.file2(g, table.in, nodesfile=nodesfile, edgesfile=edgesfile)
	} else {
	    library(rgl)
	    rn <- vire.nonascii(rownames(table.in))
	    rain = rainbow(clnb)
	    colors = rain[classes]
	    #rn <- rownames(table.in)
	    #rgl.open()
	    bg3d('white')
	    #rgl.bg(col = c('white', "#99bb99"), front = "lines", box=FALSE, sphere = TRUE)
	    
	    par3d('userMatrix' = matrix(c(1,0,0,0, 0,1,0,0,0,0,1,0,0,0,0,1), ncol=4, nrow = 4))
	    #par3d(cex=0.7)
	    #par3d(windowRect = c(100,100,600,600))
	    rgl.lines(c(rx), c(0, 0), c(0, 0), col = "#000000")
	    rgl.lines(c(0,0),c(ry),c(0,0),col = "#000000")
	    rgl.lines(c(0,0),c(0,0),c(rz),col = "#000000")
	    text3d(rx[2]+1,0,0, xlab)
	    text3d(0,ry[2]+1,0, ylab)
	    text3d(0,0,rz[2]+1, zlab)
	    splt <- split(seq_along(table.in[,1]), ceiling(seq_along(table.in[,1])/100))
	    #colsplt <- split(seq_along(colors), ceiling(seq_along(colors)/100))
	    #cexsplt <- split(seq_along(cex.par), ceiling(seq_along(cex.par)/100))
	    for (i in splt) {
	        rgl.texts(table.in[i,1], table.in[i,2], table.in[i,3], rn[i], col = colors[i] , cex = cex.par[i])
	    }
	    #rgl.texts(table.in[,1], table.in[,2], table.in[,3], rn, col = colors , cex = cex.par)
	    
	     if (tchi) {
	        maxchi <- norm.vec(maxchi, tchi.min/100, tchi.max/100)
	    } else if (!is.null(cex.par)) {
	        maxchi <- norm.vec(cex.par, txt.min/100, txt.max/100)
	    } else {
	        maxchi <- 0.1
	    }
	    
	    
	    #for (i in 1:clnb) {
	    #    text3d(rx[2],(ry[2]+(0.2*i)),0,paste('classe',i),col=rain[i])
	    #}
	    if (tchi) {
	        rgl.spheres(table.in, col = colors, radius = maxchi, alpha = alpha)
	    }
	    par3d(skipRedraw=FALSE)
	
	    if (dofilm) {
	        require(tcltk)
	        ReturnVal <- tkmessageBox(title="RGL 3 D",message="Cliquez pour commencer le film",icon="info",type="ok")
	
	        movie3d(spin3d(axis=c(0,1,0),rpm=6), movie = 'film', frames = "tmpfilm", duration=10, clean=TRUE, top = TRUE, dir = dirout)
	        ReturnVal <- tkmessageBox(title="RGL 3 D",message="Fini !",icon="info",type="ok")
	    }
	
	    if (typegraph == 1) {
	        require(tcltk)
	        ReturnVal <- tkmessageBox(title="RGL 3 D",message="Cliquez pour fermer",icon="info",type="ok")
	    } else {
	        writeWebGL(dir = fileout, width = width, height= height)
	    }
	    rgl.close()
	}
}
