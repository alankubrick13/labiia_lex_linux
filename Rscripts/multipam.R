library(cluster)

#data<-read.table('output/corpus_bin.csv',header=TRUE,sep='\t')

multipam<-function(data,x=9){
	dataori=data
	dtable=data
	a<-0
	for (m in 1:length(dtable)) {
	    if (sum(dtable[m-a])==0) {
                print('colonne vide')
		dtable<-dtable[,-(m-a)]
		a<-a+1
	    }
        }
	for (i in 1:x) {
		clnb<-(i*2)
		#construction de la matrice des distances
        dissmat<-dist(dtable,method='binary')#FIXME: rendre optionnelle la methode
        #bipartition
        pm<-pam(dissmat,diss=TRUE,k=2)
		print(pm)
		#listclasse<-ifelse(coordrow<0,paste('CLASSE',clnb,sep=''),paste('CLASSE',clnb+1,sep=''))
        #selection de la classe la moins homogène
        clusinf<-pm$clusinfo
		if (i==1){
        	listclust<-clusinf[,2]
		} else {
			listclust<-rbind(listclust,clusinf[,2])
		}
		
        listclasse=as.data.frame(pm$clustering)[,1]
        #ajout du classement au tableau
		dtable<-transform(dtable,cl1=listclasse)
		print(dtable)
		#lignes concernees
		listrownamedtable<-rownames(dtable)
		listrownamedtable<-as.integer(listrownamedtable)
        newcol<-vector(length=nrow(dataori))
		#remplissage de la nouvelle colonne avec les nouvelles classes
		num<-0
		for (ligne in listrownamedtable) {
			num<-num+1
			newcol[ligne]<-as.vector(dtable$cl1[num])[1]
		}
		#recuperation de la classe precedante pour les cases vides
		matori<-as.matrix(dataori)
        if (i!=1) {
        #    options(warn=-1)
            for (ligne in 1:length(newcol)) {
         #       print(newcol[ligne])
                if (newcol[ligne]==0) { # ce test renvoie un warning
                    newcol[ligne]<-matori[ligne,length(matori[1,])]
                }
            }
         #   options(warn=0)
        }
        #print(newcol)
		#???????????????????????????????????
		#je ne comprends pas : j'ai vraiment besoin de faire ces deux actions  pour ajouter la nouvelle colonne aux donnees ?
		#si je ne le fais pas, ca plante...
		dataori<-cbind(dataori,newcol)
		dataori<-transform(dataori,newcol=newcol)
		#???????????????????????????????????
		
		#liste des noms de colonne
		#colname<-colnames(dataori)
		#nom de la derniere colonne
		#colname<-colname[length(dataori)]
		#la derniere colonne
		colclasse<-as.character(dataori[,ncol(dataori)])
		#print(colclasse)
        #les modalites de la derniere colonne
		classes<-levels(as.factor(colclasse))
		print(classes)
		#determination de la classe la plus grande
		tailleclasse<-paste(NULL,1:length(classes))
		b<-0
		for (classe in classes) {
		   b<-b+1
		   dtable<-dataori[dataori[length(dataori)]==classe,]
		   tailleclasse[b]<-length(dtable[,1])
		}
		tailleclasse<-as.integer(tailleclasse)
		print(tailleclasse)
		plusgrand<-which(tailleclasse==max(tailleclasse))
		
		#???????????????????????????????????
		#Si 2 classes ont des effectifs egaux, on prend la premiere de la liste...
		if (length(plusgrand)>1) {
			plusgrand<-plusgrand[1]
		}
		#????????????????????????????????????
		
		#constuction du prochain tableau a analyser
		classe<-classes[plusgrand]
		dtable<-dataori[dataori[length(dataori)]==classe,]
		dtable<-dtable[,1:(length(dtable)-i)]
		#elimination des colonnes ne contenant que des 0
		a<-0
		for (m in 1:length(dtable)) {
			if (sum(dtable[m-a])==0) {
				dtable<-dtable[,-(m-a)]
				a<-a+1
			}
		}	
	}
	dataori[(length(dataori)-x+1):length(dataori)]
}

dm<-read.csv2('/home/pierre/fac/maitrise/classification/simi01.csv',row.names=1)
multipam(dm)
#dataout<-CHD(data,9)

#library(cluster)
#dissmat<-daisy(dataout, metric = 'gower', stand = FALSE)
#chd<-diana(dissmat,diss=TRUE,)


#pour tester le type, passer chaque colonne en matice et faire mode(colonne)
#for (i in 1:13) {tmp<-as.matrix(data[i]);print(mode(tmp))}
