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
#info<-read.csv2(file('/home/pierre/fac/etudiant/crepin/simi/info01.csv',encoding='latin1'),row.names=1)
#cinf<-ncol(info)
#biblio<-read.csv2(file('/home/pierre/fac/etudiant/crepin/simi/biblio01.csv',encoding='latin1'),row.names=1)
#cbib<-ncol(biblio)
#rechdoc<-read.csv2(file('/home/pierre/fac/etudiant/crepin/simi/recherdoc01.csv',encoding='latin1'),row.names=1)
#crech<-ncol(rechdoc)

######################@@
#MV
#########################
#chaud<-read.csv2('/home/pierre/fac/etudiant/sab/Chaudronnier_pour_MV01.csv',row.names=1)
##cchaud<-ncol(chaud)
#op<-read.csv2('/home/pierre/fac/etudiant/sab/ocn_pour_mv01.csv',row.names=1)
##cop<-ncol(op)
#soud<-read.csv2('/home/pierre/fac/etudiant/sab/soudeur_pour_mv01.csv',row.names=1)
##csoud<-ncol(soud)
#indus<-read.csv2('/home/pierre/fac/etudiant/sab/metier_indus01.csv',row.names=1)
##cmindus<-ncol(mindus)
#infor<-read.csv2('/home/pierre/fac/etudiant/sab/Informaticien_pour_MV01.csv',row.names=1)
##cinfor<-ncol(infor)
#trav<-read.csv2('/home/pierre/fac/etudiant/sab/travail_pour_mv01.csv',row.names=1)
##ctrav<-ncol(trav)
#tot<-cbind(chaud,op)
#tot<-cbind(tot,soud)
#tot<-cbind(tot,indus)
##
#list_data<-list('a'=chaud, 'b'=soud,'c'=infor,'d'=trav)
#tot<-cbind(chaud,op)
#tot<-chaud
##tot<-cbind(tot,infor)
##tot<-cbind(tot,trav)
#mv<-read.csv2('/home/pierre/fac/etudiant/sab/chaud_soud_opn_metierindus01.csv')
#mv<-mv[,-ncol(mv)]
#grp<-read.csv2('/home/pierre/fac/etudiant/sab/grp2.csv')
#tab<-tot

print('passe ici')
#tot<-mv[,-ncol(mv)]
#tot<-trav
#################################################
#AGIR
#ag<-read.csv2('/home/pierre/workspace/iramuteq/corpus/tableau_agir2_recod_alc_entree_pourpassage_temp_AlcesteQuest_1/Act01.csv')
#cag<-ncol(ag)
#load('/home/pierre/workspace/iramuteq/corpus/tableau_agir2_recod_alc_entree_pourpassage_temp_AlcesteQuest_1/RData.RData')

###############################################################
#Vero
#tot<-read.csv2('/home/pierre/fac/etudiant/crepin/simi/simitot01.csv')
#grp<-vector(mode='integer',length=ncol(tot))
#grp[1:54]<-1
#grp[55:108]<-2
#grp[109:162]<-3
#prof<-BuildProf01(tot,grp[,1])
##prof<-prof[-nrow(prof),]
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

###################################################################
#Steph

#tot<-read.csv2('/home/pierre/fac/etudiant/netto/simi-27-03-09/prof_inf_ecole_priv01.csv')
#tot<-tot[,-ncol(tot)]
#grp<-vector(mode='integer',length=nrow(tot))
#grp[1:245]<-1
#grp[246:490]<-2
#prof<-BuildProf01(tot,grp)
#print(nrow(prof))
##print(prof)
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

#tot<-read.csv2('/home/pierre/fac/etudiant/netto/simi-27-03-09/etu_inf_pro_priv01.csv')
#print(tot[,ncol(tot)])
#tot<-tot[,-ncol(tot)]
#grp<-vector(mode='integer',length=nrow(tot))
#grp[1:175]<-1
#grp[176:350]<-2
#prof<-BuildProf01(tot,grp)
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

#tot<-read.csv2('/home/pierre/fac/etudiant/netto/simi-27-03-09/prof_etu_inf_pro01.csv')
#print(tot[,ncol(tot)])
#tot<-tot[,-ncol(tot)]
#grp<-vector(mode='integer',length=nrow(tot))
#grp[1:245]<-1
#grp[246:419]<-2
#prof<-BuildProf01(tot,grp)
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

#######################################################
#grp ideal 2008
#tot<-read.csv2('/home/pierre/workspace/iramuteq/corpus/grpiedal2008_01.csv')
#print(tot[,ncol(tot)])
#grp<-vector(mode='integer',length=ncol(tot))
#grp[1:10]<-1
#grp[11:20]<-2
#prof<-BuildProf01(tot,grp)
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

#ministre<-read.csv2('/home/pierre/workspace/iramuteq/corpus/Ministres_AFCUCI_3/TableCont.csv',header=TRUE)
#eff<-colSums(ministre)
#ministre<-ministre[,-which(eff<100)]
#
##ministre<-(ministre/colSums(ministre))*1000
#print(ncol(ministre))
#pm<-t(ministre)
#outp<-AsLexico(pm)
#chistabletot<-outp[[2]]
#ministre<-read.csv2('/home/pierre/workspace/iramuteq/corpus/Ministres_Alceste_1/TableUc1.csv',header=TRUE)
#load('/home/pierre/workspace/iramuteq/corpus/Ministres_Alceste_1/RData.RData')
#ministre<-ministre[,-which(eff<200)]
#uce<-read.csv2('/home/pierre/workspace/iramuteq/corpus/Ministres_Alceste_1/listeUCE1.csv')
#uc<-matrix(0,nrow(ministre),1)
#uc<-list()
#print(uce)
#print(nrow(n1))
#for (i in 1:nrow(uce)) {
#    uc[[as.integer(uce[i,2])+1]]<-n1[i,ncol(n1)]
#}
#print(nrow(ministre))
#grp<-unlist(uc)
#prof<-BuildProf01(ag,n1[,ncol(n1)])
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

#######################
#Steph
#########################
#priv<-read.csv2('/home/pierre/workspace/iramuteq/corpus/simi/info_priv01.csv')
#pro<-read.csv2('/home/pierre/workspace/iramuteq/corpus/simi/info_pro01.csv')
#cpriv<-ncol(priv)
#tot<-cbind(priv,pro)
#tot<-read.csv2('/home/pierre/workspace/iramuteq/corpus/simi/priv_pro_ens01.csv')
#print('tot')
#print(ncol(tot))


#grp<-vector(mode='integer',length=nrow(tot))
#grp[1:245]<-1
#grp[246:nrow(tot)]<-2
#grp[491:635]<-3
#prof<-BuildProf01(tot,grp)
#prof<-prof[,-4]
#print(prof)
#print(nrow(prof))
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]
#cs<-colSums(prof)
#prof<-prof/cs
#l<-vector(mode='integer',length=nrow(prof))
#for (line in 1:nrow(prof)) {
#    l[line]<-as.integer(which.max(prof[line,1:2]))
#}
print('lecture')
#chistabletot<-chistabletot[1:ncol(ministre),]
#print(nrow(chistabletot))
#sc<-colSums(as.matrix(ministre))
#print(length(sc))
#outc<-which(sc>0)
#print(length(outc))
#ministre<-ministre[,outc]
#print(ncol(ministre))
#prof<-BuildProf01(ministre,grp)
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]
#chistabletot<-chistabletot[outc,]
#print(nrow(chistabletot))
#ave<-read.csv2('/home/pierre/workspace/iramuteq/corpus/Avenir_Alceste_1/TableUc1.csv',header=TRUE)
#load('/home/pierre/workspace/iramuteq/corpus/Avenir_Alceste_1/RData.RData')    
#chistabletot<-chistabletot[1:cag,]

#print(grp)
#grp<-as.character(grp[,1])
#titre<-c("chaudronnier","soudeur","informaticien","travail")
#count<-0
#split.screen(c(2,2))
#for (tab in list_data) {
#count<-count+1
#screen(count)
#par(cex=0.7)
#grp<-rbind(grp,grp)
#grp<-rbind(grp,grp)
#print(ncol(tab))

#####################################################################
#suede enfance en danger
tot<-read.csv2('/home/pierre/fac/suede/resultats/cat_asso1_01.csv',row.names=1)

#prof<-BuildProf01(tab,grp[,1])
#outp<-AsLexico(prof)
#chistabletot<-outp[[2]]

#print('liste des classes')
#listclasse<-vector(mode='integer',length=ncol(tab))
#for (line in 1:nrow(chistabletot)) {
#    if (max(chistabletot[line,])>0) {
#        listclasse[line]<-as.vector(which.max(chistabletot[line,]))
#    } else {
#        listclasse[line]<-3
#    }
#}
#classes<-listclasse
#classes<-classes[1:cag]
#print(classes)
#tot<-cbind(info,biblio)
#tot<-cbind(tot,rechdoc)
listclasse<-vector(mode='integer',length=ncol(dt))
for (line in 1:nrow(chistabletot)) {
	if ((max(chistabletot[line,])>3.84) || (min(prof[line,])==0)) {
		if (max(chistabletot[line,])>3.84) {
			listclasse[line]<-as.vector(which.max(chistabletot[line,]))
		}
		if (min(prof[line,])==0) {
			print('zero')
			listclasse[line]<-as.vector(which.max(prof[line,]))
		}
	} else {
		listclasse[line]<-3
	}
}

print('matrice de similitude')
mindus<-makesimi(tot)
m<-mindus$m
eff<-mindus$eff

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
rain<-c("green","red","white")#"yellow","pink","black")#green","blue","red","black")
vcol<-vector(mode='integer',length=length(eff))
vcolb<-vector(mode='integer',length=length(eff))
#classes<-classes[1:93]
#classes<-grp
#for (i in 1:length(eff)){
#    vcol[i]<-rain[as.integer(classes[i])]
#	vcolb[i]<-"black"
#}
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
wev<-eff*20
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
tkplot(g3,vertex.label=colnames(m),edge.width=wee,vertex.size=wev,vertex.label.color="black",layout=lo)#,vcolb vertex.label.dist=1)#,vertex.shape='none')#,edge.label=weori)
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
autre :
dm<-read.csv2('classe_mod.csv',row.names=1,header = FALSE)
load('RData.RData')
#------------------------------------------------------
#selectionner
chimax<-as.matrix(apply(chistabletot,1,max))
chimax<-as.matrix(chimax[,1][1:nrow(dm)])
chimax<-cbind(chimax,1:nrow(dm))
order_chi<-as.matrix(chimax[order(chimax[,1],decreasing = TRUE),])
elim<-which(rownames(dm) == 'faire')
dm<-dm[-elim,]
dm<-dm[chimax[,2][1:300],]
#-------------------------------------------------------
limit<-nrow(dm)
distm<-dist(dm,diag=TRUE)
distm<-as.matrix(distm)
g1<-graph.adjacency(distm,mode='lower',weighted=TRUE)
g1<-minimum.spanning.tree(g1)
lo<-layout.kamada.kawai(g1,dim=3)
mc<-rainbow(ncol(chistabletot))
chistabletot<-chistabletot[-elim,]
cc<-vector()
for (i in 1:limit) {
	cc<-append(cc,which.max(chistabletot[i,]))
}
cc<-mc[cc]
mass<-rowSums(dm)/100
rglplot(g1,vertex.label = rownames(dm),vertex.label.color=cc,vertex.color=cc,vertex.size = mass, layout=lo)



autre :
dm<-read.csv2('enseignant_simi_opi.csv',row.names=1,na.string='')
mat<-matrix(0,ncol=ncol(dm),nrow=ncol(dm))
for (i in 1:(ncol(dm)-1)) {
	for (j in (i+1):ncol(dm)){
	tab<-table(dm[,i],dm[,j])
	chi<-chisq.test(tab)
	mat[i,j]<-chi$statistic
	mat[j,i]<-chi$statistic
	}
}
mat<-ifelse(mat>3.84,mat,0)
mat<-ifelse(is.na(mat),0,mat)
mat<-ifelse(is.infinite(mat),0,mat)
cs<-colSums(mat)
tovire<-which(cs==0)
if (!is.integer(tovire)){
mat<-mat[-tovire,]
mat<-mat[,-tovire]
}
cn<-colnames(dm)
if (!is.integer(tovire)) cn<-cn[-tovire]
g1<-graph.adjacency(mat,mode='lower',weighted=TRUE)
lo<-layout.fruchterman.reingold(g1,dim=2)
wei<-E(g1)$weight
plot(g1,vertex.label=cn,vertex.size=0.1,edge.width=wei,edge.label=round(wei,2),layout=lo)



levels.n<-mj$levels.n
levelnames<-mj$levelnames
cn<-mj$colnames
count<-0
for (j in 1:ncol(dm)) {
	for (i in 1:levels.n[j]) {
		count<-count+1
		print(paste(cn[j],'\\.',sep=''))
		levelnames[count]<-gsub(paste(cn[j],'\\.',sep=''),'',levelnames[count])
	}
}
		