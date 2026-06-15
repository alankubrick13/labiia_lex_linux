#Author: Pierre Ratinaud
#Copyright (c) 2008-2020 Pierre Ratinaud
#License: GNU/GPL


#fichier genere par IRaMuTeq
source('%s')
load('%s')
doafc <- TRUE
nd <- %i
filename <-'%s'
width <- %i
height <- %i
facteurs <- '%s'
lignes <- '%s'
colonnes <- '%s'

filein <- 'tableafcm.csv'
library(ca)

if (doafc) {
    cont <- read.csv2('tableafcm.csv', header = TRUE, row.names = 1, quote='"')
    afc <- ca(cont, nd=nd)
    afc <- AddCorrelationOk(afc)
    afc <- summary.ca.dm(afc)
    afc_table <- create_afc_table(afc)
    write.csv2(afc_table$facteur, file = facteurs)
    write.csv2(afc_table$colonne, file = colonnes)
    write.csv2(afc_table$ligne, file = lignes)
}

#open_file_graph(filename, width = width, height = height)
#make_afc_graph(toplot,classes,clnb, xlab, ylab, cex_txt = NULL) 
