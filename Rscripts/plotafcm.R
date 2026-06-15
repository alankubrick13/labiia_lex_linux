#library(ca)
#datadm<-read.table('/home/pierre/.hippasos/corpus_agir.csv',header=TRUE,sep='\t',quote='\"')
#data.mjca<-mjca(datadm[,-1],supcol=c(1:12),nd=6)

tridata<-function(tabletot,nb=10,fnb=2) {
    #atrier = x
    #sumx<-summary(atrier)
    #tabletot<-as.data.frame(sumx[3])
    tabletotf1<-tabletot[order(tabletot[,5]),]
    rowkeep1<-tabletotf1[1:nb,]
    rowkeep1<-rbind(rowkeep1,tabletotf1[(nrow(tabletotf1)-nb):nrow(tabletotf1),])
    rowf1names<-rownames(rowkeep1)
    tabletotf2<-tabletot[order(tabletot[,8]),]
    rowkeep2<-tabletotf2[1:nb,]
    rowkeep2<-rbind(rowkeep2,tabletotf2[(nrow(tabletotf2)-nb):nrow(tabletotf2),])
    rowf2names<-rownames(rowkeep2)
    count<-0
    for (names in 1:length(rowf1names)) {
        for (names2 in 1:length(rowf2names)) {  
            if (rowf1names[names]==rowf2names[names2]) {
                rowkeep1<-rowkeep1[-(as.numeric(names)-count),]
                count<-count+1
                }
            }
    }
    rowkeep12<-rbind(rowkeep1,rowkeep2)
    if (fnb>=3) {
        count<-0
        row12names<-rownames(rowkeep12)
        tabletotf3<-tabletot[order(tabletot[,14]),]
        rowkeep3<-tabletotf1[1:nb,]
        rowkeep3<-rbind(rowkeep3,tabletotf3[(nrow(tabletotf3)-nb):nrow(tabletotf3),])
        rowf3names<-rownames(rowkeep3)
        for (names in 1:length(row12names)) {
            for (names3 in 1:length(rowf3names)) {
                if (rowf3names[names3]==row12names[names]) {
                    rowkeep12<-rowkeep12[-(as.numeric(names)-count),]
                    count<-count+1
                }
            }
        }
        rowkeep123<-rbind(rowkeep12,rowkeep3)
        rowkeep123
    }
    else {
        rowkeep12 }
}
#rowkeep<-tridata(data.mjca,nb=50,fnb=3)
#matrow<-as.matrix(rowkeep)
#x<-as.numeric(matrow[,5])
#y<-as.numeric(matrow[,8])
#z<-as.numeric(matrow[,11])
#labels<-matrow[,1]
#plot3d(x,y,z,xlab='',ylab='',zlab='',box=FALSE,axes=FALSE)
#text3d(x,y,z,labels)
#rgl.bg(col = c("#aaaaaa", "#99bb99"), front = "lines", box=FALSE, sphere = TRUE)
#rgl.lines(c(range(x)), c(0, 0), c(0, 0), col = "#0000ff")
#rgl.lines(c(0,0),c(range(y)),c(0,0),col = "#0000ff")
#rgl.lines(c(0,0),c(0,0),c(range(z)),col = "#0000ff")
#text3d(range(x)[2]+1,0,0,'f1')
#text3d(0,range(y)[2]+1,0,'f2')
#text3d(0,0,range(z)[2]+1,'f3')
#plot(as.numeric(matrow[,5]),as.numeric(matrow[,8]))
#text(as.numeric(matrow[,5]),as.numeric(matrow[,8]),matrow[,1])

tridata2<-function(tabletot,nb=5,fnb=2) {
	#atrier = x
	#sumx<-summary(atrier)
	#tabletot<-as.data.frame(sumx[3])
	tabletotf1<-tabletot[order(tabletot[,1]),]
	rowkeep1<-tabletotf1[1:nb,]
	rowkeep1<-rbind(rowkeep1,tabletotf1[(nrow(tabletotf1)-nb):nrow(tabletotf1),])
	rowf1names<-rownames(rowkeep1)
	tabletotf2<-tabletot[order(tabletot[,2]),]
	rowkeep2<-tabletotf2[1:nb,]
	rowkeep2<-rbind(rowkeep2,tabletotf2[(nrow(tabletotf2)-nb):nrow(tabletotf2),])
	rowf2names<-rownames(rowkeep2)
	count<-0
	for (names in 1:length(rowf1names)) {
		for (names2 in 1:length(rowf2names)) {  
			if (rowf1names[names]==rowf2names[names2]) {
				rowkeep1<-rowkeep1[-(as.numeric(names)-count),]
				count<-count+1
			}
		}
	}
	rowkeep12<-rbind(rowkeep1,rowkeep2)
	if (fnb>=3) {
		count<-0
		row12names<-rownames(rowkeep12)
		tabletotf3<-tabletot[order(tabletot[,3]),]
		rowkeep3<-tabletotf1[1:nb,]
		rowkeep3<-rbind(rowkeep3,tabletotf3[(nrow(tabletotf3)-nb):nrow(tabletotf3),])
		rowf3names<-rownames(rowkeep3)
		for (names in 1:length(row12names)) {
			for (names3 in 1:length(rowf3names)) {
				if (rowf3names[names3]==row12names[names]) {
					rowkeep12<-rowkeep12[-(as.numeric(names)-count),]
					count<-count+1
				}
			}
		}
		rowkeep123<-rbind(rowkeep12,rowkeep3)
		rowkeep123
	}
	else {
		rowkeep12 }
}

uncover<-function(tabletot,x) {
	#tabletot=tableau des coordonnées
	tabletotf1<-tabletot$table[order(tabletot$table[,x]),]
	ref<-tabletotf1[1,]
	distminx<-0.4
	distminy<-0.2
	i<-2
	#k=nrow(elim)
	if (is.null(tabletot$elim)){
		elim<-NULL#tabletot#$elim
	} else {
		elim=tabletot$elim
	}
	while (i < nrow(tabletotf1)) {
		signex<-ref[1]*tabletotf1[i,1]
		signey<-ref[2]*tabletotf1[i,2]
		if (signex>0) {
			dist<-abs(ref)-abs(tabletotf1[i,])
			dist<-abs(dist)
			print(dist)
			if (abs(dist[1])<distminx) {
				if (signey>0){
					if (abs(dist[2])<distminy) {
						elim<-rbind(elim,tabletotf1[i,])
						row.names(elim)[nrow(elim)]<-row.names(tabletotf1)[i]
						#k<-k+1
						tabletotf1<-tabletotf1[-i,]
					}else{
						ref<-tabletotf1[i,]
						i<-i+1
					}
				}else{ref<-tabletotf1[i,];i<-i+1}
				
			}else{
				ref<-tabletotf1[i,]
			#	print(ref)
				i<-i+1
			}
		}else {
			ref<-tabletotf1[i,]
			i<-i+1
		}
	} 
	print(length(tabletotf1))
	elim<-elim[-1,]
	out<-list()
	out$table<-tabletotf1
	out$elim<-elim
	out
	
}
#ntb<-tabletot[order(tabletot[,1]),]
#ntb2<-uncover(ntb)
#ntb2$table<-ntb2$table[order(ntb2$table[,2]),]
#ntb2$table<-uncover(ntb2$table)



#		if (tabletotf1[i,1])
#		ref<-
#	}
#	rowkeep1<-tabletotf1[1:nb,]
#	rowkeep1<-rbind(rowkeep1,tabletotf1[(nrow(tabletotf1)-nb):nrow(tabletotf1),])
#	rowf1names<-rownames(rowkeep1)
#	tabletotf2<-tabletot[order(tabletot[,2]),]
#	rowkeep2<-tabletotf2[1:nb,]
#	rowkeep2<-rbind(rowkeep2,tabletotf2[(nrow(tabletotf2)-nb):nrow(tabletotf2),])
#	rowf2names<-rownames(rowkeep2)
#	count<-0
#	for (names in 1:length(rowf1names)) {
#		for (names2 in 1:length(rowf2names)) {  
#			if (rowf1names[names]==rowf2names[names2]) {
#				rowkeep1<-rowkeep1[-(as.numeric(names)-count),]
#				count<-count+1
#			}
#		}
#	}
#	rowkeep12<-rbind(rowkeep1,rowkeep2)
#	if (fnb>=3) {
#		count<-0
#		row12names<-rownames(rowkeep12)
#		tabletotf3<-tabletot[order(tabletot[,3]),]
#		rowkeep3<-tabletotf1[1:nb,]
#		rowkeep3<-rbind(rowkeep3,tabletotf3[(nrow(tabletotf3)-nb):nrow(tabletotf3),])
#		rowf3names<-rownames(rowkeep3)
#		for (names in 1:length(row12names)) {
#			for (names3 in 1:length(rowf3names)) {
#				if (rowf3names[names3]==row12names[names]) {
#					rowkeep12<-rowkeep12[-(as.numeric(names)-count),]
#					count<-count+1
#				}
#			}
#		}
#		rowkeep123<-rbind(rowkeep12,rowkeep3)
#		rowkeep123
#	}
#	else {
#		rowkeep12 }
#}
