#Author: Pierre Ratinaud
#Copyright (c) 2015-2016 Pierre Ratinaud
#License: GNU/GPL

#Distance de Labbe
###########
#NEED TEST#
###########


compute.labbe <- function(x, y, tab) {

    mini.tab <- tab[,c(x, y)]

    cs <- colSums(mini.tab)

    N1 <- cs[1]
    N2 <- cs[2]

    plus.grand <- ifelse(N1>N2, 1,2)
    plus.petit <- ifelse(N1>N2, 2,1)

    if (plus.grand == 1) {
        U <- N2/N1
        mini.tab[,1] <- mini.tab[,1] * U
		col.plusgrand <- mini.tab[,1]
		cs.plus.grand <- sum(col.plusgrand[col.plusgrand>=1])
    } else {
        U <- N1/N2
        mini.tab[,2] <- mini.tab[,2] * U
		col.plusgrand <- mini.tab[,2]
		cs.plus.grand <- sum(col.plusgrand[col.plusgrand>1])
    }
    commun <- which((mini.tab[,1] > 0) & (mini.tab[,2] > 0))
    deA <- which((mini.tab[,plus.petit] > 0) & (mini.tab[,plus.grand] == 0))
    deB <- which((mini.tab[,plus.petit] == 0)  & (mini.tab[,plus.grand] >= 1))

    dist.commun <- abs(mini.tab[commun, plus.petit] - mini.tab[commun, plus.grand])
    dist.deA <- abs(mini.tab[deA, plus.petit] - mini.tab[deA, plus.grand])
    dist.deB <- abs(mini.tab[deB, plus.petit] - mini.tab[deB, plus.grand])
    dist.labbe <- sum(dist.commun) + sum(dist.deA) + sum(dist.deB)

    indice.labbe <- dist.labbe/(cs[plus.petit] + cs.plus.grand)
    indice.labbe
}

#calcul pour distance texte 1 et 2
#compute.labbe(1,2,tab)

dist.labbe <- function(tab) {
	mat <- matrix(NA, ncol=ncol(tab), nrow=ncol(tab))
	rownames(mat) <- colnames(tab)
	colnames(mat) <- colnames(tab)
	for (i in 1:(ncol(tab)-1)) {
		for (j in (1+i):ncol(tab)) {
			#lab <- compute.labbe(i,j,tab)
			mat[j,i] <- compute.labbe(i,j,tab)
		}
	}
    mat
}

