AssignClasseToUce<-function(listuce,chd) {
	out<-matrix(nrow=nrow(listuce),ncol=ncol(chd))
	for (i in 1:nrow(listuce)) {
		for (j in 1:ncol(chd)) {
			out[i,j]<-chd[(listuce[i,2]+1),j]
		}
	}
	out
}



pamtxt <- function(dm, listucein, uceout, method = 'binary', clust_type = 'pam', clnb = 3) {
	listuce <- read.csv2(listucein)
	x <- read.csv2(dm, header = FALSE)
	library(cluster)
	x <- as.matrix(x)
	distmat <- dist(x,method = method)
	if (clust_type == 'pam')
    	cl <- pam(distmat, clnb, diss=TRUE)
	else if (clust_type == 'fanny')
		cl <- fanny(distmat, clnb, diss=TRUE, memb.exp = 1.001)
	cld <- as.data.frame(cl$clustering)
	colnames(cld) <- 'classes'
    out <- as.data.frame(AssignClasseToUce(listuce,cld))
	write.csv2(out[,1],uceout)
	result <- list(uce = out, cl = cl)
	result
} 
