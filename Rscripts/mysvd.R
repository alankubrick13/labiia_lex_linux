#http://www.mail-archive.com/rcpp-devel@lists.r-forge.r-project.org/msg01513.html

write.sparse <- function (m, to) {
  ## Writes in a format that SVDLIBC can read
  stopifnot(inherits(m, "dgCMatrix"))
  fh <- file(to, open="w")
  
  wl <- function(...) cat(..., "\n", file=fh)
  
  ## header
  wl(dim(m), length(m@x))
  
  globalCount <- 1
  nper <- diff(m@p)
  for(i in 1:ncol(m)) {
    wl(nper[i])  ## Number of entries in this column
    if (nper[i]==0) next
    for(j in 1:nper[i]) {
      wl(m@i[globalCount], m@x[m@p[i]+j])
      globalCount <- globalCount+1
    }
  }
}

write.sparse2 <- function(m, to) {
    stopifnot(inherits(m, "dgCMatrix"))
    fh <- file(to, open="w")
  
    wl <- function(...) cat(..., "\n", file=fh)
    wl(dim(m), length(m@x))   

}

print('FIXME : svdpath hardcoded !!')
my.svd <- function(x, nu, nv) {
  stopifnot(nu==nv)
  rc <- system(paste("/usr/bin/svd -o /tmp/sout -d", nu, "/tmp/sparse.m"))
  if (rc != 0)
    stop("Couldn't run external svd code")
  d <- scan("/tmp/sout-S", skip=1)
#FIXME : sometimes, svdlibc doesn't find solution with 2 dimensions, but does with 3 
  if (length(d)==1) {
      nu <- nu + 1
      rc <- system(paste("/usr/bin/svd -o /tmp/sout -d", nu, "/tmp/sparse.m"))
      d <- scan("/tmp/sout-S", skip=1)
  }
  ut <- matrix(scan('/tmp/sout-Ut',skip=1),nrow=nu,byrow=TRUE)
  if (nrow(ut)==3) {
      ut <- ut[-3,]
  }
  vt <- NULL
  list(d=d, u=-t(ut), v=vt)
}
