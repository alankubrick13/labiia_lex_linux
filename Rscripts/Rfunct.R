ColType <- function(x) {
#x data.frame
    type<-character()
    for (i in 1:ncol(x)) {
        tmp<-as.matrix(x[,i])
        type[i]<-mode(tmp)
    }
    type
}

LevelsNb<- function(x) {
    levelsnb<-numeric()
    for (i in 1:ncol(x)) {
        if (mode(as.matrix(x[,i]))=="character") {
            levelsnb[i]<-length(levels(x[,i]))
        }
        else {
            levelsnb[i]<-NA
        }
    }
    levelsnb
}

ReadData<- function(filename,sep=';',quote='"', header=TRUE, encoding='', na.strings ='',rownames=NULL) {
    if (version$os=='linux-gnu') {
        dataimport<-read.csv2(file(filename,encoding=encoding), header=header, sep=sep, quote=quote, na.strings='',row.names=rownames)
    } else {
        dataimport<-read.csv2(filename,encoding=encoding, header=header,sep=sep, quote=quote,na.strings='',row.names=rownames)
    }
    dataimport
}
            
testzero<-function(mydata) {
    nc<-vector()
    nl<-vector()
    for (i in 1:ncol(mydata)) {
        if (sum(mydata[,i])==0) {
            print('zero')
            nc<-append(nc,i)
        }
    }
    print('suite')
    for (j in 1:nrow(mydata)) {
        print(j)
        if (sum(mydata[j,])==0) {
            print('zero')
            nl<-append(nl,j)
        }
    }
    c(nc,nl)
}
