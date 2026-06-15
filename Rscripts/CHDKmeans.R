#Author: Pierre Ratinaud
#Copyright (c) 2008 Pierre Ratinaud
#Lisense: GNU/GPL



#library(ca)
#library(MASS)
#source('/home/pierre/workspace/iramuteq/Rscripts/afc.R')
#data<-read.table('output/corpus_bin.csv',header=TRUE,sep='\t')
#source('/home/pierre/workspace/iramuteq/Rscripts/anacor.R')
#library(ade4)
pp<-function(txt,val) {
	d<-paste(txt,' : ')
	print(paste(d,val))
}
MyChiSq<-function(x,sc,n){
	sr<-rowSums(x)
	E <- outer(sr, sc, "*")/n
	STAT<-sum((abs(x - E))^2/E)
	STAT
}

CHD<-function(data,x=9){
#	sink('/home/pierre/workspace/iramuteq/dev/findchi2.txt')
	dataori=as.matrix(data)
	row.names(dataori)=rownames(data)
	dtable=as.matrix(data)
	row.names(dtable)=rownames(data)
	rowelim<-NULL
	pp('ncol entree : ',ncol(dtable))
	pp('nrow entree',nrow(dtable))
	listcol <- list()
	listmere <- list()
	list_fille <- list()
	print('vire colonnes vides en entree')#FIXME : il ne doit pas y avoir de colonnes vides en entree !!
	sdt<-colSums(dtable)
	if (min(sdt)==0)
		dtable<-dtable[,-which(sdt==0)]
	mere<-1
	for (i in 1:x) {
		clnb<-(i*2)
		listmere[[clnb]]<-mere
		listmere[[clnb+1]]<-mere
		list_fille[[mere]] <- c(clnb,clnb+1)
		listcol[[clnb]]<-vector()
		listcol[[clnb+1]]<-vector()
		#extraction du premier facteur de l'afc
		print('afc')
		#afc<-ca(dtable,nd=1)
		#afc<-corresp(dtable,nd=1)
		#afc<-fca(dtable)
		pp('taille dtable dans boucle (col/row)',c(ncol(dtable),nrow(dtable)))
#		afc<-boostana(dtable,nd=1)
#		#afc<-dudi.coa(dtable,scannf=FALSE,nf=1)
#		pp('SV',afc$singular.values)
#		pp('V.P.', afc$eigen.values)
#		#pp('V.P.',afc$eig[1])
#		#pp('V.P.',afc$factexpl[1])
#		#print(afc$chisq)
#		afcchi<-chisq.test(dtable)
#		Tinert<-afcchi$statistic/sum(dtable)
#		pp('inertie totale',Tinert)
#		#coordonnees des colonnes sur le premier facteur
#		#coordrow=afc$rowcoord
#		coordrow=as.matrix(afc$row.scores)
#		#coordrow<-as.matrix(afc$rproj[,1])
#		#coordrow<-as.matrix(afc$li)
#		coordrowori<-coordrow
#		#row.names(coordrow)<-afc$rownames
#		row.names(coordrow)<-rownames(dtable)
#		#classement en fonction de la position sur le premier facteur
#		print('deb recherche meilleur partition')
#		ordertable<-cbind(dtable,coordrow)
#		coordrow<-as.matrix(coordrow[order(coordrow[,1]),])
#		ordertable<-ordertable[order(ordertable[,ncol(ordertable)]),][,-ncol(ordertable)]
#		listinter<-vector()
#		listlim<-vector()
		TT=sum(dtable)
#		sc<-colSums(dtable)
#		sc1<-ordertable[1,]
#		sc2<-colSums(dtable)-ordertable[1,]
#		chitable<-rbind(sc1,sc2)
#		#listinter<-vector()
#		maxinter<-0
#		rmax<-NULL
##################################################################
#		for (l in 2:(nrow(dtable)-2)){
#			chitable[1,]<-chitable[1,]+ordertable[l,]
#			chitable[2,]<-chitable[2,]-ordertable[l,]
##			sc1<-sc1+ordertable[l,]
##			sc2<-sc2-ordertable[l,]
##			chitable<-rbind(sc1,sc2)
#			chi<-MyChiSq(chitable,sc,TT)
#			if (chi>maxinter) {
#				maxinter<-chi
#				rmax<-l
#			}
#		#	listinter<-append(listinter,MyChiSq(chitable,sc,TT))#,chisq.test(chitable)$statistic/TT)
#		}
#		#plot(listinter)
#		print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@')
#		pp('max inter phase 1', maxinter/TT)#max(listinter))
#		print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@')
#		#maxinter<-which.max(listinter)+1
#
#		listclasse<-ifelse(coordrowori<=coordrow[(rmax),1],clnb,clnb+1)
#		
#		cl<-listclasse
#
#		pp('TT',TT)
#		#dtable<-cbind(dtable,'cl'= as.vector(cl))
#
#		N1<-length(listclasse[listclasse==clnb])
#		N2<-length(listclasse[listclasse==clnb+1])
#		pp('N1',N1)
#		pp('N2',N2)
####################################################################
##                  reclassement des individus                     #
####################################################################
#		malcl<-1000000000000
#		it<-0
#		listsub<-list()
#		#in boucle
#
#		while (malcl!=0 & N1>=5 & N2>=5) {
#			it<-it+1
#			listsub[[it]]<-vector()
#			pp('nombre iteration',it)
#			vdelta<-vector()
#			#dtable[,'cl']<-cl
#			t1<-dtable[cl==clnb,]#[,-ncol(dtable)]
#			t2<-dtable[cl==clnb+1,]#[,-ncol(dtable)]
#			ncolt<-ncol(t1)
#			pp('ncolt',ncolt)
#			sc1<-colSums(t1)
#			sc2<-colSums(t2)
#			sc<-sc1+sc2
#			TT<-sum(dtable)
#			chtableori<-rbind(sc1,sc2)
#			interori<-MyChiSq(chtableori,sc,TT)/TT#chisq.test(chtableori)$statistic#/TT
#			chtable<-chtableori
#			pp('interori',interori)
#			N1<-nrow(t1)
#			N2<-nrow(t2)
#			pp('N1',N1)
#			pp('N2',N2)
#			
#			for (l in 1:nrow(dtable)){
#					if(cl[l]==clnb){
#						chtable[1,]<-sc1-dtable[l,]
#						chtable[2,]<-sc2+dtable[l,]
#					}else{
#						chtable[1,]<-sc1+dtable[l,]
#						chtable[2,]<-sc2-dtable[l,]
#					}
#					interswitch<-MyChiSq(chtable,sc,TT)/TT#chisq.test(chtable)$statistic/TT
#					ws<-interori-interswitch
#
#					if (ws<0){
#						interori<-interswitch
#						if(cl[l]==clnb){
#							sc1<-chtable[1,]
#							sc2<-chtable[2,]
#							cl[l]<-clnb+1
#							listsub[[it]]<-append(listsub[[it]],l)
#						}else{
#							sc1<-chtable[1,]
#							sc2<-chtable[2,]
#							cl[l]<-clnb
#							listsub[[it]]<-append(listsub[[it]],l)
#						}
#						vdelta<-append(vdelta,l)
#					}
#				}
##			for (val in vdelta) {
##				if (cl[val]==clnb) {
##					cl[val]<-clnb+1
##					listsub[[it]]<-append(listsub[[it]],val)
##					}else {
##					cl[val]<-clnb
##					listsub[[it]]<-append(listsub[[it]],val)
##				}
##			}
#			print('###################################')
#			print('longueur < 0')
#			malcl<-length(vdelta)
#			if ((it>1)&&(!is.logical(listsub[[it]]))){
#				if (listsub[[it]]==listsub[[(it-1)]]){
#					malcl<-0
#				}
#			}
#			print(malcl)
#			print('###################################')
#		}
##########################################################################
# kmeans
#        clori<-kmeans(dtable,2)$cluster
#        cl<-ifelse(clori==1,clnb,clnb+1)
#pam
        library(cluster)
        clori<-pam(dist(dtable,method='binary'),2,diss=TRUE)$cluster
        cl<-ifelse(clori==1,clnb,clnb+1)
        
            dtable<-cbind(dtable,'cl'=as.vector(cl))

#######################################################################
#                 Fin reclassement des individus                      #
#######################################################################
#		if (!(length(cl[cl==clnb])==1 || length(cl[cl==clnb+1])==1)) {
			t1<-dtable[dtable[,'cl']==clnb,][,-ncol(dtable)]
			t2<-dtable[dtable[,'cl']==clnb+1,][,-ncol(dtable)]
		
			chtable<-rbind(colSums(t1),colSums(t2))
			inter<-chisq.test(chtable)$statistic/TT
			pp('last inter',inter)
			print('=====================')
			
			#calcul de la specificite des colonnes
			mint<-min(nrow(t1),nrow(t2))
			maxt<-max(nrow(t1),nrow(t2))
			seuil<-round((1.9*(maxt/mint))+1.9,digit=6)
			#sink('/home/pierre/workspace/iramuteq/dev/findchi2.txt')
#			print('ATTENTION SEUIL 3,84')
#			seuil<-3.84
			pp('seuil',seuil)
			sominf<-0
			nv<-0
			nz<-0
			ncclnb<-0
			ncclnbp<-0
            NN1<-0
            NN2<-0
            maxchip<-0
            nbzeroun<-0
            res1<-0
            res2<-0
            nbseuil<-0
            nbexe<-0
            nbcontrib<-0
			cn<-colnames(dtable)[1:(ncol(dtable)-1)]
			for (k in 1:(ncol(dtable)-1)) {
				#print(k)
				tab<-table(dtable[,k],dtable[,ncol(dtable)])
				#print(cn[k])
				#print (tab)
				#chidemoi<-(sum(t)*(((t[1,1]*t[2,2])-(t[1,2]*t[2,1]))^2))/((rowSums(t)[1])*(rowSums(t)[2])*(colSums(t)[1])*(colSums(t)[2]))
				if (rownames(tab)[1]==1 & nrow(tab)==1) {
					tab<-rbind(c(0,0),tab[1])
					print('tableau vide dessus')
				}
				if (min(tab)<=10){
					chi<-chisq.test(tab,correct=TRUE)
				}else{
					chi<-chisq.test(tab,correct=FALSE)
				}
				if ((min(tab[2,])==1) & (min(tab[1,])!=0)){
					chi$statistic<-seuil+1
				#    print('min tab 2 == 0')	
				}
#                if(((tab[2,1]>tab[1,1]) & (tab[2,2]>tab[1,2]))){
#					nz<-nz+1
#					chi$statistic<-seuil-1
#					sominf<-sominf-1
#				}
                if ((min(tab[1,])==0) & (min(tab[2,])!=0)){
					chi$statistic<-seuil-1
                #    print('min tab 1 == 0')
				}
				if (is.na(chi$statistic)) {
					chi$statistic<-0
					print('NA dans chi$statistic')
				}
#				print('#####################')
				if (chi$statistic>seuil){
				i#	print('sup seuil')
					if (tab[2,1]<chi$expected[2,1]){
						listcol[[clnb]]<-append(listcol[[clnb]],cn[k])
						ncclnb<-ncclnb+1
#						print('@@@@@@@@specifique de la classe@@@@@@')
#						print(clnb)
					} else if (tab[2,2]<chi$expected[2,2]){
						listcol[[clnb+1]]<-append(listcol[[clnb+1]],cn[k])
						ncclnbp<-ncclnbp+1
#						print('@@@@@@@@specifique de la classe@@@@@@')
#						print(clnb+1)
					}
				}
#				if (chi$statistic<seuil){
#					print('inf seuil')
#					print(tab)
#					print(chi$expected)
#					print(chi$statistic)
#					sominf<-sominf+1
#				}
				
#				print('tableau')
#				print(tab)
#				chi<-chisq.test(tab,correct=FALSE)
#				print('sans correction')
#				print(chi$statistic)
#				print(chi$expected)
#				print(chi$residuals)
#                chit<-((tab-chi$expected)^2)/chi$expected
#                print(mean(chi$residuals))
#                print(sd(as.vector(chi$residuals)))
                #print(chi$residuals/sd(as.vector(chi$residuals)))
                #print(abs(chi$residuals/sd(as.vector(chi$residuals))))
                #print(qnorm(abs(chi$residuals/sd(as.vector(chi$residuals)))))
#                difftab<-tab-chi$expected
 #               print('contribution')
                #print((difftab-mean(difftab))/sd(as.vector(difftab)))
                #print(abs((chit-mean(chit))/sd(as.vector(chit))))
#                tabin1<-matrix(1,2,2)
#                tabin1<-tabin1-(colSums(tab)/sum(tab))
#                tabin2<-matrix(1,2,2)
#                tabin2<-(tabin2-(rowSums(tab)/sum(tab)))
#                tabinv<-tabin1*tabin2
#                CS<-colSums(tab)
#                RS<-rowSums(tab)
#                GT<-sum(tab)
#                print(tabinv)
#                contrib<-(tab-chi$expected)/sqrt(chi$expected * ((1 - RS/GT) %*% t(1 - CS/GT)))
#                print(chit)
#                print('TTTTTTTTTTTTTTTTTTTTTTTTTTTTTT')
#                print(contrib)
#                if (((which.max(chit)==2) || (which.max(chit)==4)) & chi$statistic>=seuil) {
#                    if (which.max(chit)==2) NN1<-NN1+1
#                    if (which.max(chit)==4) NN2<-NN2+1
#                }
#                if (max(abs(contrib[2,])>=1.96)) {
#                    nbcontrib<-nbcontrib+1
#                }
#                if (max(chit[2,]>=seuil)) maxchip<-maxchip+1
#                if (chi$statistic >=seuil) nbseuil<-nbseuil+1
#                if ((min(tab[2,])==0) & (chi$statistic<seuil)) nbzeroun<-nbzeroun+1
#                if ((((which.max(chi$residual)==2) || (which.max(chi$residual)==4) || (which.min(chi$residual)==2) || (which.min(chi$residual)==4))) & chi$statistic>=seuil) {
#                    if ((which.max(chi$residual)==2) || (which.min(chi$residual)==4)) res1<-res1+1
#                    if ((which.max(chi$residual)==4) || (which.min(chi$residual)==2)) res2<-res2+1
#                } else if (!((which.max(chi$residual)==2) || (which.max(chi$residual)==4) || (which.min(chi$residual)==2) || (which.min(chi$residual)==4)) & chi$statistic>=seuil) {
#                    print('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
#                    print('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
#                }
#                if (length(unique(as.vector(chi$residual)))==2) {
#                    nbexe<-nbexe+1
#                }

#				print('avec correction')
#                if (min(tab)<5) chi<-chisq.test(tab,correct=TRUE)
#				print(chi$statistic)
#                #if (chi$statistic >=seuil) nbseuil<-nbseuil+1
#				print(chi$expected)
#				print(chi$residuals)
#                chit<-((abs(tab-chi$expected)-0.5)^2)/chi$expected
#                print(chit)
#				print('#####################')
			}
#            pp('NN1',NN1)
#            pp('NN2',NN2)
#            pp('maxchip',maxchip)
#            pp('nbzeroun',nbzeroun)
#            pp('res1',res1)
#            pp('res2',res2)
#            pp('nbseuil',nbseuil)
#            pp('nbexe',nbexe)
#            pp('nbcontrib', nbcontrib)
			print('resultats elim item')
			pp(clnb+1,length(listcol[[clnb+1]]))
			pp(clnb,length(listcol[[clnb]]))
#			pp('inf seuil',sominf)
#			pp('nv',nv)
			pp('ncclnb',ncclnb)
			pp('ncclnbp',ncclnbp)
#			pp('nz',nz)
			#sink()
			#lignes concernees
			listrownamedtable<-rownames(dtable)
			listrownamedtable<-as.integer(listrownamedtable)
			newcol<-vector(length=nrow(dataori))
			#remplissage de la nouvelle colonne avec les nouvelles classes
			print('remplissage')
			num<-0
			for (ligne in listrownamedtable) {
				num<-num+1
				newcol[ligne]<-as.integer(as.vector(dtable[,'cl'][num])[1])
			}
			#recuperation de la classe precedante pour les cases vides
			print('recuperation classes precedentes')
			matori<-as.matrix(dataori)
			if (i!=1) {
				#    options(warn=-1)
				for (ligne in 1:length(newcol)) {
					#       print(newcol[ligne])
					if (newcol[ligne]==0) { # ce test renvoie un warning
						if (ligne %in% rowelim){
							newcol[ligne]<-0
						} else {
							newcol[ligne]<-matori[ligne,length(matori[1,])]
						}
						
					}
				}
				#   options(warn=0)
			}
			dataori<-cbind(dataori,newcol)
			
			tailleclasse<-as.matrix(summary(as.factor(as.character(dataori[,ncol(dataori)]))))
			#tailleclasse<-as.integer(tailleclasse)
			print('tailleclasse')
			print(tailleclasse)
			tailleclasse<-as.matrix(tailleclasse[!(rownames(tailleclasse)==0),])
			plusgrand<-which.max(tailleclasse)
			#???????????????????????????????????
			#Si 2 classes ont des effectifs egaux, on prend la premiere de la liste...
			if (length(plusgrand)>1) {
				plusgrand<-plusgrand[1]
			}
			#????????????????????????????????????
			
			#constuction du prochain tableau a analyser
			print('construction tableau suivant')
			classe<-as.integer(rownames(tailleclasse)[plusgrand])
			dtable<-dataori[dataori[,ncol(dataori)]==classe,]
			row.names(dtable)<-rownames(dataori[dataori[,ncol(dataori)]==classe,])
			dtable<-dtable[,1:(ncol(dtable)-i)]
			mere<-classe
			listcolelim<-listcol[[as.integer(classe)]]
			mother<-listmere[[as.integer(classe)]]
			while (mother!=1) {
				listcolelim<-append(listcolelim,listcol[[mother]])
				mother<-listmere[[mother]]
			}
			
			listcolelim<-sort(unique(listcolelim))
			pp('avant',ncol(dtable))
			if (!is.logical(listcolelim)){
				print('elimination colonne')
				#dtable<-dtable[,-listcolelim]
				dtable<-dtable[,!(colnames(dtable) %in% listcolelim)]
			}
			pp('apres',ncol(dtable))
			#elimination des colonnes ne contenant que des 0
			print('vire colonne inf 3 dans boucle')
			sdt<-colSums(dtable)
			if (min(sdt)<=3)
				dtable<-dtable[,-which(sdt<=3)]
	
			#elimination des lignes ne contenant que des 0
			print('vire ligne vide dans boucle')
			if (ncol(dtable)==1) {
				sdt<-dtable[,1]
			} else {
				sdt<-rowSums(dtable)
			}
			if (min(sdt)==0) {
				rowelim<-as.integer(rownames(dtable)[which(sdt==0)])
				print('&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&')
				print(rowelim)
				print('&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&')
				dtable<-dtable[-which(sdt==0),]
			}
#		}
	}
#	sink()
	res <- list(n1 = dataori[,(ncol(dataori)-x+1):ncol(dataori)], list_mere = listmere, list_fille = list_fille)
	res
}

#dataout<-CHD(data,9)

#igraph pour graph de relation
