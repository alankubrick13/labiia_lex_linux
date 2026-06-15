#Author: Pierre Ratinaud
#Copyright (c) 2008-2009 Pierre Ratinaud
#License: GNU/GPL

fille<-function(classe,classeuce) {
	listfm<-unique(unlist(classeuce[classeuce[,classe%/%2]==classe,]))
	listf<-listfm[listfm>=classe]
	listf<-unique(listf)
	listf
}


croiseeff <- function(croise, classeuce1, classeuce2) {
    cl1 <- 0
    cl2 <- 1
    for (i in 1:ncol(classeuce1)) {
        cl1 <- cl1 + 2
        cl2 <- cl2 + 2
        clj1 <- 0
        clj2 <- 1
        for (j in 1:ncol(classeuce2)) {
            clj1 <- clj1 + 2
            clj2 <- clj2 + 2
            croise[cl1 - 1, clj1 -1] <- length(which(classeuce1[,i] == cl1 & classeuce2[,j] == clj1))
            croise[cl1 - 1, clj2 -1] <- length(which(classeuce1[,i] == cl1 & classeuce2[,j] == clj2))
            croise[cl2 - 1, clj1 -1] <- length(which(classeuce1[,i] == cl2 & classeuce2[,j] == clj1))
            croise[cl2 - 1, clj2 -1] <- length(which(classeuce1[,i] == cl2 & classeuce2[,j] == clj2))
        }
    }
    croise
}


#fonction pour la double classification
#cette fonction doit etre splitter en 4 ou 5 fonctions

Rchdquest<-function(tableuc1,listeuce1,uceout ,nbt = 9, mincl = 2, mode.patate = FALSE, svd.method = 'irlba') {
	#source('/home/pierre/workspace/iramuteq/Rscripts/CHD.R')
    if (svd.method == 'irlba') {
        library(irlba)
    }
	#lecture des tableaux
	data1<-read.csv2(tableuc1)#,row.names=1)
    cn.data1 <- colnames(data1)
    data1 <- as.matrix(data1)
    colnames(data1) <- cn.data1
    rownames(data1) <- 1:nrow(data1)
	data2<-data1
	sc<-colSums(data2)
	if (min(sc)<=4){
		data1<-data1[,-which(sc<=4)]
		sc<-sc[-which(sc<=4)]
	}
	#analyse des tableaux avec la fonction CHD qui doit etre sourcee avant
	chd1<-CHD(data1, x = nbt, mode.patate = mode.patate, svd.method)
	chd2<-chd1

	#FIXME: le nombre de classe peut etre inferieur
    nbcl <- nbt + 1
    tcl <- ((nbt+1) * 2) - 2

	#lecture des uce
	listuce1<-read.csv2(listeuce1)
	listuce2<-listuce1

	#Une fonction pour assigner une classe a chaque UCE
#	AssignClasseToUce<-function(listuce,chd) {
#	    out<-matrix(nrow=nrow(listuce),ncol=ncol(chd))
#	    for (i in 1:nrow(listuce)) {
#			for (j in 1:ncol(chd)) {
#			    out[i,j]<-chd[(listuce[i,2]+1),j]
#			}
#	    }
#	    out
#	}

    AssignClasseToUce <- function(listuce, chd) {
        print('assigne classe -> uce')
        chd[listuce[,2]+1,]
    }
	#Assignation des classes
	classeuce1<-AssignClasseToUce(listuce1,chd1$n1)
	classeuce2<-classeuce1
	
	#calcul des poids (effectifs)
	poids1<-vector(mode='integer',length=tcl)
#	makepoids<-function(classeuce,poids) {
#	    for (classes in 2:(tcl + 1)){
#		for (i in 1:ncol(classeuce)) {
#		    if (poids[(classes-1)]<length(classeuce[,i][classeuce[,i]==classes])) {
#		        poids[(classes-1)]<-length(classeuce[,i][classeuce[,i]==classes])
#		    }
#		}
#	    }
#	    poids
#	}
    makepoids <- function(classeuce, poids) {
        cl1 <- 0
        cl2 <- 1
        for (i in 1:nbt) {
            cl1 <- cl1 + 2
            cl2 <- cl2 + 2
            poids[cl1 - 1] <- length(which(classeuce[,i] == cl1))
            poids[cl2 - 1] <- length(which(classeuce[,i] == cl2))
        }
        poids
    }
    
	poids1<-makepoids(classeuce1,poids1)
	poids2<-poids1

#	croise=matrix(ncol=tcl,nrow=tcl)
#	#production du tableau de contingence
#	for (i in 1:ncol(classeuce1)) {
#	    #poids[i]<-length(classeuce1[,i][x==classes])
#	    for (j in 1:ncol(classeuce2)) {
#		tablecroise<-table(classeuce1[,i],classeuce2[,j])
#		tabcolnames<-as.numeric(colnames(tablecroise))
#		#tabcolnames<-c(tabcolnames[(length(tabcolnames)-1)],tabcolnames[length(tabcolnames)])
#		tabrownames<-as.numeric(rownames(tablecroise))
#		#tabrownames<-c(tabrownames[(length(tabrownames)-1)],tabrownames[length(tabrownames)])
#		for (k in (ncol(tablecroise)-1):ncol(tablecroise)) {
#		    for (l in (nrow(tablecroise)-1):nrow(tablecroise)) {
#		        croise[(tabrownames[l]-1),(tabcolnames[k]-1)]<-tablecroise[l,k]
#		    }
#		}
#	    }
#	    tablecroise
#	}
    croise <- croiseeff( matrix(ncol=tcl,nrow=tcl), classeuce1, classeuce2)
    if (mincl == 2) {
	    mincl<-round(nrow(classeuce1)/(nbt+1)) #valeur a calculer nbuce/nbt
    }
    #print('ATTENTION MINCL IMPOSE')
	#mincl<-422
	print('mincl')
	print(mincl)
	if (mincl < 3) {
	    mincl<-3
	}
    #print('ATTENTION : ON IMPOSE LA TAILLE DES CLASSES')
    #mincl <- 15
	print('table1')
	print(croise)
	#tableau des chi2 signes
	chicroise<-croise
	for (i in 1:nrow(croise)) {
	    for (j in 1:ncol(croise)) {
		if (croise[i,j]==0) {
		    chicroise[i,j]<-0
		} else if (croise[i,j]<mincl) { 
		    chicroise[i,j]<-0
		} else {
			chitable<-matrix(ncol=2,nrow=2)
			chitable[1,1]<-croise[i,j]
			chitable[1,2]<-poids1[i]-chitable[1,1]
			chitable[2,1]<-poids2[j]-chitable[1,1]
			chitable[2,2]<-nrow(classeuce1)-poids2[j]-chitable[1,2]
			chitest<-chisq.test(chitable,correct=FALSE)
			if ((chitable[1,1]-chitest$expected)<0) {
			    chicroise[i,j]<--round(chitest$statistic,digits=7)
			} else {
			    chicroise[i,j]<-round(chitest$statistic,digits=7)
		#print(chitest)
			}
		}
	    }   
	}
	print(chicroise)
	#determination des chi2 les plus fort
	chicroiseori<-chicroise
    doxy <- function(chicroise) {
        listx <- NULL
        listy <- NULL
        listxy <- which(chicroise > 3.84, arr.ind = TRUE)
        #print(listxy)
        val <- chicroise[which(chicroise > 3.84)]
        ord <- order(val, decreasing = TRUE)
        listxy <- listxy[ord,]
        #for (i in 1:nrow(listxy)) {
        #    if ((!listxy[,2][i] %in% listx) & (!listxy[,1][i] %in% listy)) {
        #        listx <- c(listx, listxy[,2][i])
        #        listy <- c(listy, listxy[,1][i])
        #    }
        #}
        xy <- list(x = listxy[,2], y = listxy[,1])
        xy
    }
    xy <- doxy(chicroise)
    print(xy)
    listx <- xy$x
    listy <- xy$y
    
#	maxi<-vector()
#	chimax<-vector()
#	for (i in 1:tcl) {
#	    maxi[i]<-which.max(chicroise)
#	    chimax[i]<-chicroise[maxi[i]]
#	    chicroise[maxi[i]]<-0
#	}
#	testpres<-function(x,listcoord) {
#	    for (i in 1:length(listcoord)) {
#		if (x==listcoord[i]) {
#		    return(-1)
#		} else {
#		    a<-1
#		}
#	    }
#	    a
#	}
#	c.len=nrow(chicroise)
#	r.len=ncol(chicroise)
#	listx<-c(0)
#	listy<-c(0)
#	rang<-0
#	cons<-list()
#	#on garde une valeur par ligne / colonne
#	for (i in 1:length(maxi)) {
#	#coordonnées de chi2 max
#	    x.co<-ceiling(maxi[i]/c.len)
#	    y.co<-maxi[i]-(x.co-1)*c.len
#	    a<-testpres(x.co,listx)
#	    b<-testpres(y.co,listy)
#	    
#	    if (a==1) {
#		if (b==1) {
#		    rang<-rang+1
#		    listx[rang]<-x.co
#		    listy[rang]<-y.co
#		}
#	    }
#	    cons[[1]]<-listx
#	    cons[[2]]<-listy
#	}
	#pour ecrire les resultats
	for (i in 1:length(listx)) {
	    txt<-paste(listx[i]+1,listy[i]+1,sep=' ')
	    txt<-paste(txt,croise[listy[i],listx[i]],sep=' ')
	    txt<-paste(txt,chicroiseori[listy[i],listx[i]],sep=' ')
	    print(txt)
	}

	#colonne de la classe
	#trouver les filles et les meres 
	trouvefillemere<-function(classe,chd) {
	    unique(unlist(chd[chd[,classe%/%2]==classe,]))
	}

	#pour trouver une valeur dans une liste
	#is.element(elem, list)
	#== elem%in%list

	coordok<-NULL
	trouvecoordok<-function(first) {
	    fillemere1<-NULL
	    fillemere2<-NULL
	    listxp<-listx
	    listyp<-listy
	    listxp<-listx[first:length(listx)]
	    listxp<-c(listxp,listx[1:(first-1)])
	#    listxp<-listxp[-first]
	    listyp<-listy[first:length(listy)]
	    listyp<-c(listyp,listy[1:(first-1)])
	#    listyp<-listyp[-first]
	    for (i in 1:length(listxp)) {
	       if (!(listxp[i]+1)%in%fillemere1) {
		  if (!(listyp[i]+1)%in%fillemere2) {
		  coordok<-rbind(coordok,c(listyp[i]+1,listxp[i]+1))
		  fillemere1<-c(fillemere1,trouvefillemere(listxp[i]+1,chd2$n1))
		  fillemere2<-c(fillemere2,trouvefillemere(listyp[i]+1,chd1$n1))
		  }
	       }
	    }
	    coordok
	}
#fonction pour trouver le nombre maximum de classes
	findmaxclasse<-function(listx,listy) {
	    listcoordok<-list()
	    maxcl<-0
	    nb<-1
	    for (i in 1:length(listy)) {

		coordok<-trouvecoordok(i)
		if (maxcl <= nrow(coordok)) {
		    maxcl<-nrow(coordok)
		    listcoordok[[nb]]<-coordok
		    nb<-nb+1
		}
	    }
	    listcoordok<-unique(listcoordok)
		print('liste coord ok')
#		print('FIXME FIXME FIXME FIXME FIXME')
#		print(listcoordok)
		#si plusieurs ensemble avec le meme nombre de classe, on conserve
		#la liste avec le plus fort chi2
	    if (length(listcoordok)>1) {
		maxchi<-0
		best<-NULL
		for (i in 1:length(listcoordok)) {
		    chi<-NULL
		    uce<-NULL
		    if (nrow(listcoordok[[i]])==maxcl) {
		        for (j in 1:nrow(listcoordok[[i]])) {
		            chi<-c(chi,croise[(listcoordok[[i]][j,1]-1),(listcoordok[[i]][j,2]-1)])
		            uce<-c(uce,chicroiseori[(listcoordok[[i]][j,1]-1),(listcoordok[[i]][j,2]-1)])
		        }
				print(sum(uce))
		        if (maxchi < sum(chi)) {
		            maxchi<-sum(chi)
		            suce<-sum(uce)
		            best<-i
		        } 
		    }
		}
	    }
	    print((suce/nrow(classeuce1)*100))
	    listcoordok[[best]]
	}
	#findmaxclasse(listx,listy)
	#coordok<-trouvecoordok(1)
	coordok<-findmaxclasse(listx,listy)
	print(coordok)

	fille<-function(classe,classeuce) {
	    listfm<-unique(unlist(classeuce[classeuce[,classe%/%2]==classe,]))
	    listf<-listfm[listfm>=classe]
	    listf<-unique(listf)
	    listf
	}


	lfilletot<-function(classeuce) {
	    listfille<-NULL
	    for (classe in 1:nrow(coordok)) {
		listfille<-unique(c(listfille,fille(coordok[classe,1],classeuce)))
		listfille
	    }
	}

	listfille1<-lfilletot(classeuce1)
	listfille2<-lfilletot(classeuce2)


	#utiliser rownames comme coordonnees dans un tableau de 0
	Assignclasse<-function(classeuce,x) {
	    nchd<-matrix(0,ncol=ncol(classeuce),nrow=nrow(classeuce))
	    for (classe in 1:nrow(coordok)) {
		
		clnb<-coordok[classe,x]
		colnb<-clnb%/%2
		tochange<-which(classeuce[,colnb]==clnb)
	    for (row in 1:length(tochange)) {
		    nchd[tochange[row],colnb:ncol(nchd)]<-classe
		}
	    }
	    nchd
	}
	print('commence assigne new classe')
	nchd1<-Assignclasse(classeuce1,1)
	#nchd1<-Assignnewclasse(classeuce1,1)
	nchd2<-Assignclasse(classeuce2,2)
	print('fini assign new classe')
	croisep<-matrix(ncol=nrow(coordok),nrow=nrow(coordok))
	for (i in 1:nrow(nchd1)) {
	    if (nchd1[i,ncol(nchd1)]==0) {
		nchd2[i,]<-nchd2[i,]*0
	    }
	    if (nchd1[i,ncol(nchd1)]!=nchd2[i,ncol(nchd2)]) {
		nchd2[i,]<-nchd2[i,]*0
	    }
	    if (nchd2[i,ncol(nchd2)]==0) {
		nchd1[i,]<-nchd1[i,]*0
	    }
	}
	print('fini croise')
	elim<-which(nchd1[,ncol(nchd1)]==0)
	keep<-which(nchd1[,ncol(nchd1)]!=0)
	n1<-nchd1[nchd1[,ncol(nchd1)]!=0,]
	n2<-nchd2[nchd2[,ncol(nchd2)]!=0,]
	print('debut graph')
	clnb<-nrow(coordok)
	print('fini')
	write.csv2(nchd1[,ncol(nchd1)],uceout)
	res <- list(n1 = nchd1, coord_ok = coordok, cuce1 = classeuce1, chd = chd1)
	res
}
#n1<-Rchdtxt('/home/pierre/workspace/iramuteq/corpus/agir2sortie01.csv','/home/pierre/workspace/iramuteq/corpus/testuce.csv','/home/pierre/workspace/iramuteq/corpus/testuceout.csv')
