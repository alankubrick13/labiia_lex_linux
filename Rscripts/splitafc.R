#library(ca)
#datadm<-read.csv2(file('TableCont.csv', encoding='utf-8'))
#afc<-ca(datadm, nd=3)
plotqrtafc<- function(afc,x=1,y=2,supcol=NA,filename='afcdiv4_',width=480,height=480,quality=75,reso=200,ptsize=12,PARCEX=PARCEX) {
    if (is.na(supcol)) {
        noc<-afc$colnames
        colcoord<-afc$colcoord
    }
    else {
        noc<-afc$colnames[supcol[1]:supcol[2]]
        colcoord<-afc$colcoord[supcol[1]:supcol[2],]
    }
    fiqrt<-data.frame()
    seqrt<-data.frame()
    foqrt<-data.frame()
    thqrt<-data.frame()
    for (i in 1:(nrow(colcoord))) {
        if (colcoord[,x][i]<0) {
            if (colcoord[,y][i]<0) {
                foqrt[i,1]<-colcoord[i,x]
                foqrt[i,2]<-colcoord[i,y]
                foqrt[i,3]<-noc[i]
            }
            else {
                fiqrt[i,1]<-colcoord[i,x]
                fiqrt[i,2]<-colcoord[i,y]
                fiqrt[i,3]<-noc[i]
            }
        }
        else {
            if (colcoord[,2][i]<0) {
                thqrt[i,1]<-colcoord[i,x]
                thqrt[i,2]<-colcoord[i,y]
                thqrt[i,3]<-noc[i]
            }
            else {
                seqrt[i,1]<-colcoord[i,x]
                seqrt[i,2]<-colcoord[i,y]
                seqrt[i,3]<-noc[i]
            }
        }
    }   
    list_name<-c('hg','bg','hd','bd')
    list_table<-list(fiqrt,foqrt,seqrt,thqrt)
    for (i in 1:4) {
	    if (Sys.info()["sysname"]=='Darwin') {
	    	width<-width/74.97
	    	height<-height/74.97
	    	print(list_name[i])
	    	quartz(file=paste(filename,x,y,list_name[i],'.jpeg',sep=''),type='jpeg',width=width,height=height)#,pointsize=5)
	    } else {
	    	jpeg(paste(filename,x,y,list_name[i],'.jpeg',sep=''),quality=quality,pointsize=ptsize,res=reso,width=width,height=height)
	    }
	    par(cex=PARCEX)
		#par(mar=c(0.01,0.01,0.01,0.01))
	    plot(list_table[[i]][,1],list_table[[i]][,2],pch='')
	    text(list_table[[i]][,1],list_table[[i]][,2],list_table[[i]][,3])
	    dev.off()
	}
#    jpeg(paste(filename,x,y,'bg','.jpeg',sep=''),quality=quality,pointsize=ptsize,res=reso,width=width,height=height)
#    par(cex=PARCEX)
#    plot(foqrt[,1],foqrt[,2],pch='')
#    text(foqrt[,1],foqrt[,2],foqrt[,3])
#    dev.off()
#    jpeg(paste(filename,x,y,'hd','.jpeg',sep=''),quality=quality,pointsize=ptsize,res=reso,width=width,height=height)
#    par(cex=PARCEX)
#    plot(seqrt[,1],seqrt[,2],pch='')
#    text(seqrt[,1],seqrt[,2],seqrt[,3])
#    dev.off()
#    jpeg(paste(filename,x,y,'bd','.jpeg',sep=''),quality=quality,pointsize=ptsize,res=reso,width=width,height=height)
#    par(cex=PARCEX)
#    plot(thqrt[,1],thqrt[,2],pch='')
#    text(thqrt[,1],thqrt[,2],thqrt[,3])
#    dev.off()
}

#plotqrtafc(afc,x=1,y=2,PARCEX=0.7,quality=100,ptsize=12,reso=200,width=1000,height=1000)
