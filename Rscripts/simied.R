#############################################################
makesimi<-function(dm){
	a<-dm
	m<-matrix(0,ncol(dm),ncol(dm))
	rownames(m)<-colnames(a)
	colnames(m)<-colnames(a)
	eff<-colSums(a)
	for (col in 1:(ncol(a)-1)){
		for (colc in (col+1):ncol(a)){
			ta<-table(a[,col],a[,colc])
			if (ncol(ta)==1 & colnames(ta)[1]=='0') {
				ta<-cbind(ta,'1'=c(0,0))
			} else if (ncol(ta)==1 & colnames(ta)[1]=='1') {
				ta<-cbind('0'=c(0,0),t)
			} else if (nrow(ta)==1 & rownames(ta)[1]=='0'){
				ta<-rbind(ta,'1'=c(0,0))
			} else if (nrow(ta)==1 & rownames(ta)[1]=='1') {
				ta<-rbind('0'=c(0,0),ta)
			}
			#m[colc,col]<-length(which((a[,col]==1) & (a[,colc]==1))) 
			m[colc,col]<-ta[2,2]
			m[col,colc]<-m[colc,col]
		}
	}
	out<-list(mat=m,eff=eff)
} 


makesimip<-function(dm){
	a<-dm
	m<-matrix(0,ncol(dm),ncol(dm))
	rownames(m)<-colnames(a)
	colnames(m)<-colnames(a)
	eff<-colSums(a)
	for (col in 1:(ncol(a)-1)){
		for (colc in (col+1):ncol(a)){
			ta<-table(a[,col],a[,colc])
			if (ncol(ta)==1 & colnames(ta)[1]=='0') {
				ta<-cbind(ta,'1'=c(0,0))
			} else if (ncol(ta)==1 & colnames(ta)[1]=='1') {
				ta<-cbind('0'=c(0,0),t)
			} else if (nrow(ta)==1 & rownames(ta)[1]=='0'){
				ta<-rbind(ta,'1'=c(0,0))
			} else if (nrow(ta)==1 & rownames(ta)[1]=='1') {
				ta<-rbind('0'=c(0,0),ta)
			}
			#m[colc,col]<-length(which((a[,col]==1) & (a[,colc]==1))) 
			m[colc,col]<-ta[2,2]
			m[col,colc]<-m[colc,col]
		}
	}
	m<-round((m/nrow(a))*100,digits=0)
	out<-list(mat=m,eff=eff)
}


makejac<-function(dm){
	a<-dm
	m<-matrix(0,ncol(dm),ncol(dm))
	rownames(m)<-colnames(a)
	colnames(m)<-colnames(a)
	eff<-colSums(a)
	for (col in 1:(ncol(a)-1)){
		for (colc in (col+1):ncol(a)){
			ta<-table(a[,col],a[,colc])
			if (ncol(ta)==1 & colnames(ta)[1]=='0') {
				ta<-cbind(ta,'1'=c(0,0))
			} else if (ncol(ta)==1 & colnames(ta)[1]=='1') {
				ta<-cbind('0'=c(0,0),t)
			} else if (nrow(ta)==1 & rownames(ta)[1]=='0'){
				ta<-rbind(ta,'1'=c(0,0))
			} else if (nrow(ta)==1 & rownames(ta)[1]=='1') {
				ta<-rbind('0'=c(0,0),ta)
			}
			m[colc,col]<-(ta[2,2]/(ta[1,2]+ta[2,1]+ta[2,2]))*100
			#m[colc,col]<-(length(which((a[,col]==1) & (a[,colc]==1)))/(eff[col]+eff[colc]-length(which((a[,col]==1) & (a[,colc]==1)))))*100
			m[col,colc]<-m[colc,col]
		}
	}
	out<-list(mat=m,eff=eff)
}

makesimipond<-function(dm) {
	a<-dm
	m<-matrix(0,ncol(dm),ncol(dm))
	rownames(m)<-colnames(dm)
	colnames(m)<-colnames(dm)
	eff<-colSums(a)
	#a<-t(a)
	#print(a)
	#lt<-list()
	for (col in 1:(ncol(a)-1)){
		for (colc in (col+1):ncol(a)){
			m[colc,col]<-length(which((a[,col]>1) & (a[,colc]>1)))
			m[col,colc]<-m[colc,col]
		}
	}
	out<-list(mat=m,eff=eff)
}

BuildProf01<-function(x,classes) {
	#x : donnees en 0/1
	#classes : classes de chaque lignes de x
	dm<-cbind(x,cl=classes)
	clnb=length(summary(as.data.frame(as.character(classes)),max=100))
	print(clnb)
	print(summary(as.data.frame(as.character(classes)),max=100))
	mat<-matrix(0,ncol(x),clnb)
	#print(mat)
	rownames(mat)<-colnames(x)
	for (i in 1:clnb) {
		dtmp<-dm[which(dm$cl==i),]
		for (j in 1:(ncol(dtmp)-1)) {
			#print(rownames(dtmp[j,]))
			mat[j,i]<-sum(dtmp[,j])
		}
	}
	mat
}
###################################################################

source('/home/pierre/workspace/iramuteq/Rscripts/chdfunct.R')

#}
print('lecture')


#####################################################################
#suede enfance en danger
#ed<-read.csv2('/home/pierre/fac/suede/resultats/enfance_en_danger01.csv')
#coop<-read.csv2('/home/pierre/fac/suede/resultats/cooperation01.csv')
#as<-read.csv2('/home/pierre/fac/suede/resultats/as01.csv')
#ed<-ed[,-ncol(ed)]
#coop<-coop[,-ncol(coop)]
#as<-as[,-ncol(as)]
##tot<-tot[,-ncol(tot)]
#tot<-cbind(ed,coop)
#tot<-cbind(tot,as)
#tot<-as
#
#tot<-read.csv2('/home/pierre/fac/suede/resultats/as_catper01.csv',row.names=1)
##tot<-read.csv2('/home/pierre/fac/suede/resultats/swedish_as601.csv',row.names=1)
##print(tot)
#tot<-tot[,-ncol(tot)]
#pn<-tot[nrow(tot),]
#tot<-tot[-nrow(tot),]
#prof<-BuildProf01(tab,grp[,1])
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

##########################################################
#SUP
ens<-read.csv2('/home/pierre/fac/SUP/resultats/enseignant01.csv',row.names=1)
vp<-read.csv2('/home/pierre/fac/SUP/resultats/vieprivee01.csv',row.names=1)
tt<-read.csv2('/home/pierre/fac/SUP/resultats/asso_ens_vp01.csv',row.names=1)
ens<-ens[,-ncol(ens)]
vp<-vp[,-ncol(vp)]
tot<-tt[,-ncol(tt)]
print(nrow(tot))
gr<-vector(mode='integer',length=nrow(tot))
gr[1:41]<-1
gr[42:82]<-2

mat<-BuildProf01(tot,cl=gr)
prof<-AsLexico(mat)
chis<-prof[[2]]
print(chis)
#tot<-tot[,-ncol(tot)]
#print(tot)
#as<-vector(mode='integer',length=ncol(tot))
#as[1:ncol(ens)]<-'red'
#as[ncol(ens)+1:ncol(tot)]<-'green'
#print('liste des classes')
#listclasse<-vector(mode='integer',length=ncol(tab))
for (line in 1:nrow(chistabletot)) {
    if (max(chistabletot[line,])>2) {
        listclasse[line]<-as.vector(which.max(chistabletot[line,]))
    } else {
        listclasse[line]<-3
    }
}
#classes<-listclasse
#classes<-classes[1:cag]
#print(classes)
#tot<-cbind(info,biblio)
#tot<-cbind(tot,rechdoc)



print('matrice de similitude')
mindus<-makesimip(tot)
m<-mindus$m
eff<-mindus$eff

cn<-paste(colnames(m),eff,sep=' ')
#mateff<-makesimipond(ministre)
#mateff<-makesimi(tot)  
#mateff<-makejac(tot)
#m<-mateff$mat
#eff<-mateff$eff
#m<-as.matrix(dist(t(ministre),method='binary',upper=TRUE, diag=TRUE))
#m<-as.matrix(simil(ministre), method='Jaccard', upper=TRUE, diag=TRUE, by_rows=FALSE)
#print(nrow(m))
#print(ncol(m))
#print(length(colnames(ministre)))
#colnames(m)<-colnames(ministre)
#rownames(m)<-colnames(ministre)
#eff<-colSums(ministre)
#mateffp<-makesimi(ministre)
#mateffp<-makesimipond(ministre)
#m<-mateffp$mat
#eff<-mateffp$eff

#matave<-makesimi(ministre)
#m<-matave$m
#eff<-matave$eff

print('couleur')
#rain<-rainbow(3)
#append(rain,'black')
rain<-c("green","red","white","blue")#"yellow","pink","black")#green","blue","red","black")
vcol<-vector(mode='integer',length=length(eff))
vcolb<-vector(mode='integer',length=length(eff))
#classes<-classes[1:93]
#classes<-grp
for (i in 1:nrow(chis)) {
	vcolb[i]<-which.max(chis[i,])
}
print(vcolb)
for (i in 1:length(eff)){
	#if (as.integer(pn[i])==0){
	#	pn[i]<-4
	#	print('zero')
	#}
    #vcol[i]<-rain[as.integer(pn[i])]
	vcol[i]<-rain[as.integer(vcolb[i])]
	}
#ll<-which(effp>=0.5)
#for (i in which(effp>=0.5)) {
#	if (i<=10) {
#		vcol[i]<-"blue"
#	} else {
#		vcol[i]<-"pink"
#	}
#}
#print('length(vcol)')
#print(length(vcol))
#vcol[1:cchaud]<-rain[1]
#vcol[(cchaud+1):(cchaud+cop)]<-rain[2]
#vcol[(cchaud+cop+1):length(eff)]<-rain[3]
#print(classes)
print('premier graph')
library(igraph)
#sink('graph.txt')
g1<-graph.adjacency(m,mode="lower",weighted=TRUE)

#maxtree<-maxgraph(g1)
#plot(maxtree, layout=layout.circle)
#lo<-layout.circle(g1)
eff<-(eff/max(eff))
weori<-get.edge.attribute(g1,'weight')
#tdel<-which(weori<3)
we<-(weori/max(weori))*4
print('arbre maximum')
invw<-1/weori
E(g1)$weight<-invw
g3<-minimum.spanning.tree(g1)
E(g3)$weight<-1/E(g3)$weight
#print(E(g3)$weight)
#sink()
#g3<-g1
wev<-eff*30
wee<-(E(g3)$weight/max(E(g3)$weight))*10
weori<-E(g3)$weight
print('layout')
#lo<-layout.kamada.kawai(g3,dim=3)
lo<-layout.fruchterman.reingold(g3,dim=3)
print('lo')
#print(nrow(lo))
#lo<-layout.sphere(g3)
#lo<-cbind(lo,eff)
vsize<-vector(mode='integer',length=nrow(lo))
#print(we)
#ecount(g1)
#g2<-simplify(g1)
#g2<-delete.edges(g2,tdel-1)
#tmax<-clusters(g1)
#print(tmax)
#we<-we[-tdel]
#weori<-weori[-tdel]
#plot(g1,vertex.label=colnames(m),edge.width=get.edge.attribute(g1,'weight'),layout=layout.circle,vertex.shape='none')
#igraph.par('print.edge.attributes',TRUE)
#plot(g2,vertex.label=colnames(m),vertex.size=vsize,vertex.color=vcol,edge.width=we,layout=lo)#,vertex.shape='none')#,edge.label=weori)
#rglplot(g3,vertex.label=colnames(m),edge.width=we,vertex.size=vsize,vertex.label.color=vcol,layout=lo,vertex.shape='none')#,edge.label=weori)
print('plot')
tkplot(g3,vertex.label=cn,edge.width=wee,vertex.size=wev,vertex.color=vcol,vertex.label.color="black",edge.label=weori,layout=lo)#,vcolb vertex.label.dist=1)#,vertex.shape='none')#,edge.label=weori)
#},vertex.color=vcol
#rgl.bg(sphere=FALSE,color=c("black","white"))
#vertex.color=vcol,vertex.label.color=vcol,edge.label=weori,
#rgl.viewpoint(zoom=0.6)
#movie3d(spin3d(axis=c(0,1,0),rpm=6),10,dir='/home/pierre/workspace/iramuteq/corpus/',movie="vero_cooc_explo",clean=TRUE,convert=TRUE,fps=20)
#tkplot(g1,vertex.label=colnames(m),layout=layout.circle,vertex.shape='rectangle')
#rglplot(g1,vertex.label=colnames(m),layout=layout.circle)
#g1<-graph(m)
#tkplot(g1)





#Ministre
