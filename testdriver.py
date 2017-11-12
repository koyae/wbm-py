""" Below, take a bunch of WBM-files which appear alongside WAV-files of
matching names from a directory, and write out a single
table-of-contents file describing where each bookmark is found. """

execfile("wbm.py")

import navtools
import os

def list_qualified(qualifier,path):
   return (n for n in os.listdir(path) if qualifier(n))

def ebn(path):
	return os.path.splitext(os.path.basename(path))[0]

readdir = r"C:\tmp\k8"
os.chdir(readdir)

wbms = list_qualified(lambda a: ".wbm" in a, readdir)
bookmarkDict = {}

for wbm in wbms:
	bookmarks = get_bookmarks(wbm, os.path.splitext(wbm)[0]+".wav")
	bookmarkDict[ebn(wbm)+".wav"] = bookmarks
  
toc = []
gen = get_filename_generator(fileCount,dest="C:\\tmp",useExt=".wav",middlefix="") 
for spans in bookmarkDict.values():
    toc.extend(copy_pieces(spans,fnGen=gen))

handle = open("C:\\tmp\\k8_toc.txt",'w')
handle.write("\n\n".join(toc))
handle.close()
