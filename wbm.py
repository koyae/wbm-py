# -*- coding: cp1252 -*-
from copy import copy,deepcopy
from math import ceil,log10,log
from datetime import *
from time import *

import bitstring
import wave
import os
import re


def get_bookmarks(wbmpath,wavpath=None,tidyFunc=None,shiftHackFirst=False):
    """ -> list of dictionaries describing the bookmarks found in `wbmpath`
    See docstring of next_mark() for information about dictionary-keys.

wbmpath        --  Path to a .wbm-file which contains one or more bookmarks.

tidyFunc        --  Optional. Function. A function or other object with callable
                    signature func(string) which returns a cleaned-up string.
                    Use this if you have odd characters in the names/descriptions
                    of your bookmarks.

shiftHackFirst  --  Optional. Boolean. Whether or not the first bookmark in the
                    file is off by a factor of 16. Leave false unless you're
                    sure this is true for the particular .wbm you're using.
    """
    handle = open(wbmpath,'rb')
    info = []
    result=None
    filePosition=0
    try:
        while 1:
            result = next_mark(handle,startAt=filePosition,tidyFunc=tidyFunc)
            filePosition = result[1]
            info.append(result[0])
    except BufferError,e:
        print "Reached end of file '{}'.".format(wbmpath)
    finally:
        try: handle.close()
        except: pass
    if shiftHackFirst: info[0]['framepos'] *= 16
##    papertap(info)
    add_frame_conversions(info,wavpath)
    return info

        
def next_mark(handle,startAt=0,tidyFunc=None):
    """ open .wbm file-handle -> (dictionary describing next bookmark,nextByte)

handle      --  An open file-handle to a .wbm wav bookmark file.
                Usually the results of open('filename.wbm','rb')

                
startAt     --  Integer. 0 or byte at which the namelength descriptor field
                begins. Throughout the function, this variable is incremented
                in order to provide the next `startAt` value.

*Return value*

    This function returns a dictionary of the form given below:

    { "rawname" : <string>, # the bookmark's name/description as read from .wbm
      "name"    : <string>, # the bookmark's name after cleanup via tidyname()
      "fn"      : <string>, # the basename of the sound-file the .wbm describes
      "framepos": <int>,    # position of bookmark measured in samples (frames)
      "lucky"   : <string>, # unknown meaning. reliably "\x77\x00"
      "lonely"  : <string>, # unknown meaning. reliably "\x01\00"
      "id"      : <int>,    # the bookmark's id-number (always positive)
      "vizn"    : <int>,    # the number of times the bookmark has been visited
      "epoch"   : <int>,    # seconds relative to 1970 last visit occurred
      "lastviz" : <string>  # human-legible timestamp version of 'epoch'
    }

    If add_frame_conversions() is executed on the dictionary, you'll also
    have the additional keys:

    { "secpos"  : <float>,  # bookmark's position represented in seconds
      "minpos"  : <float>,  # bookmark's position represented in minutes
      "hmspos"  : <tuple>,  # bookmark's position as (hour, minute, second)
      "bytepos" : <int>,    # bookmark's position into file's CONTENT-bytes
                            # .. which begin immediately after the audio-file's
                            # .. header
    }
                    
"""
    ############################################################################
    # helper functions: ########################################################
    def read_and_advance(length,startAt,post=None,shoutstring=""):
        """(byte source, bytecount to read, global position in file, cleanup fx)
           -> new byte-position.

        I use this function because some behavior under Windows for
        fileHandle.tell() is not reliable, presumably because of a bad
        C-language implementation which Python relies on the operating system
        to provide.
        
        I've seen a few problems:

            1. Consecutive calls to tell() fail to return the same
            result even though no read()s or seek()s have been performed.

            2. The return-value of tell() is not reliable between calls,
            possibly due to issue 1, described above.

        """
        if shoutstring: shout(shoutstring)
        post = post if callable(post) else lambda a:a
        raw = handle.read(length)
        if not raw: raise BufferError("EOF or otherwise failed to read bytes.")
        data = post(raw)
        newPos = startAt + length
        if shoutstring:
            s = "Data: {0} ({1}) starting at {2} (x{2:X}), "
            s += "stopping just before {3} (x{3:X})"
            print s.format(repr(data),repr(raw),startAt,newPos)
            shout(shoutstring)
        return data,newPos

    def process_posix_time(data):
        """ (4-byte time-relative-to-epoch data) -> positive or negative int """
        return decrt(data,bytecount=4)
    ######################################################## :helper functions #
    ############################################################################
    tidyFunc = tidyname if not tidyFunc else tidyFunc
    if not startAt:
        handle.seek(7,os.SEEK_CUR) # allows header info be skipped
        startAt = handle.tell()
    else: handle.seek(startAt)
    markdict = {}
    namelength,startAt = read_and_advance(1,startAt,decr)
    if namelength == 0xFF:
        namelength,startAt = read_and_advance(4,startAt,decr)
    # ^ namelength is only used literally for values 254 and below, if the
    # ^.. bookmark's name/description is any longer than that, we read the
    # ^.. next 4 bytes as that number instead, and the first xFF is passed over
    markdict["rawname"],startAt = read_and_advance(namelength,startAt)
    markdict["name"] = tidyFunc( markdict["rawname"] ) # bookmark name
    fnlength,startAt = read_and_advance(1,startAt,dec)
    fn,startAt = read_and_advance(fnlength,startAt)
    markdict["fn"] = fn # parent file name
    markdict["framepos"],startAt = read_and_advance(8,startAt,decr)
    markdict["lucky"],startAt = read_and_advance(2,startAt)
    markdict["lonely"],startAt = read_and_advance(2,startAt)
    markdict["id"],startAt = read_and_advance(4,startAt,decr)
    markdict["vizn"],startAt = read_and_advance(1,startAt,dec)
    markdict["epoch"],startAt = read_and_advance(4,startAt,process_posix_time)
    markdict["lastviz"] = strftime("%x %X",
                                   ( datetime(1970,1,1,0,0,0)
                                     + timedelta(0,markdict["epoch"])
                                   ).timetuple()
                                  )
    return markdict,startAt+1


def tidyname(text):
    """ (str) -> str. Tidy up the name of a bookmark after it's been read. """
    weirdChars = {'\xc2\xA0':' ', # nbsp -> regular space
                  '\xc3\xA9':'é', # accented 'e'
                  '\xe2\x80\x94':'-', # map long dash / em dash -> hyphen
                  '\xe2\x80\x98':'\'', # opening single quote -> straight single
                  '\xe2\x80\x99':'\'' # closing single quote -> straight single
                 }
    # ^ use the above mapping to replace characters from bookmark-names
    # ^.. before kicking out filename
    for k,v in dnumerate(weirdChars):
        text = text.replace(k,v)
    # remove double spaces:
    while "  " in text:
        text = text.replace("  "," ")
    return text


def add_frame_conversions(bookmarks,parentfile=None):
    """ iterable of bookmark-dictionaries -> None. Adds human-legible times
    to bookmarks. See bookmark-dictionary documentation under next_mark() for
    more info.

bookmarks  -- Iterable (such as a list). A collection of bookmarks *ALL
              REFERRING TO THE SAME PARENT-FILE; passing bookmarks with mixed
              parent-files will result in an exception.
              
parentfile -- String. Optional. Full path to the file which the bookmarks
              describe.

    """
    if not parentfile:
        parentfile = bookmarks[0]["fn"]
        for bm in bookmarks:
            if bm["fn"] != parentfile:
                raise ValueError(" Please specify a file to read; source "
                                 + " bookmark-set references multiple files:\n"
                                 + str( list((bm["fn"] for bm in bookmarks)) )
                                )
    try:
        pf = WaveReadWrapper(parentfile)
        for bm in bookmarks:
            framepos = bm["framepos"]
            bm["bytepos"] =  framepos * pf.getsampwidth()
            bm["secpos"] = secpos = framepos/float(pf.getframerate())
            bm["minpos"] = secpos/60.0
            bm["hmspos"] = ( int(secpos//3600),
                             int(secpos//60),
                             secpos%60
                           )
    except Exception, e:
        print "Could not open parent file '{}'. Sorry.".format(parentfile)
    finally:
        try: pf.close()
        except: pass



class WaveReadWrapper(object):
    """ (filename) -> instance.

    Class that provides all of the functionality of wave.Wave_read objects, plus
    a few extra bits of information helpful for understanding a bit more about
    the loaded file. """

    def __init__(self,filename):
        self.open(filename)
        

    def open(self,filename):
        """ (file path) -> None. Open a new file. """
        wavehandle = wave.open(filename,'rb')
##        print dir(wavehandle)
        duration = wavehandle.getnframes() / float(wavehandle.getframerate())
        self.sec_duration = duration
        self.candy = wavehandle
        self.contentbyten = ( wavehandle.getsampwidth()
                              * wavehandle.getnframes() )
        # update dictionary:
##        owndict = copy(self.__dict__)
##        self.__dict__.update(wavehandle.__dict__)
##        self.__dict__.update(owndict)
        # :update_dictionary
        
    def __dir__(self):
        """ Magic method primarily used to provide proper calltips to IDEs. """
        # Transparently expose Wave_read internals along with own attributes:
        dirl = deepcopy(dir(self.candy))
        dirl.extend( self.__dict__.keys() )
        return dirl
        

    def __getattr__(self,attr):
        """ Magic method used to expose wrapped wave.Wave_read object. """
        # expose everything else from the wrapped object:
        return getattr(self.candy,attr)


    
def bindisplay(decimal,mingroups=0):
    """ (int,groupcount) -> string. Given a decimal, display as unsigned binary
    with bits grouped into sets of 4.
    """
    if decimal<0: raise NotImplementedError("Func doesn't do negatives yet.")
    s = bin(decimal).replace('0b','')
    fillamount = (4-len(s)%4)+len(s)
    # ^ fill to nearest halfbyte
    if len(s)%4 < mingroups:
        fillamount=mingroups*4
    s = s.rjust(fillamount,'0')
    reg = re.compile('\d\d\d\d')
    return reg.subn('\g<0> ',s)[0].strip()


def dec(s,pre=None,post=None):
    """ To decimal from binary data as string, then to something else if desired

s   --  hex string like "\x00\x00\x00\x2a"

pre --  optional function to run on the list/string ahead of time
        e.g. r() for little-endian hex numbers
        
post -- optional function to format the resulting integer, generally for display
        e.g. convert to group binary or simmilar
        
"""
    pre = (lambda a:a) if not pre else pre
    post = (lambda a:a) if not post else post
    f = lambda a: "{:0>02X}".format(ord(a))
    # ^ here, we format hex ints without the '0x' prefix, and pad with a
    # ^.. leading 0 if we would have a single-digit hex-character.
    # ^.. e.g.: we'd show '05' instead of just '5'
    s = pre(s)
    s = s if type(s)==type([]) else list(s)
    s = map(f, s)
    s = ''.join(s)
    return post(int(s,16))


def decf(s,pre=None):
    """ -> float. Convert bits/bytes representing an unsigned int. """
    return dec(s,pre,float)


def decr(s,post=None):
    """ Convert bits/bytes representing an unsigned little-endian integer """
    return dec(s,r,post)


def decrt(s,bitcount=None,bytecount=None):
    """ Convert bits/bytes representing a two's-complement little-endian int """
    post = lambda a: two(a,bitcount,bytecount)
    return dec(s,r,post)


def dectest(s):
    """(space-delimited pairs of characters representing little-endian hex bits)
    -> int.

    Example: dectest("00 01") -> 256
    """
    if type(s) != type([]): s = s.split(" ")
    s.reverse()
    return int("".join(s),16)


def burp(s):
    """ (str) -> str. Remove the spaces found in a string. """
    s = s.replace(' ','')
    return s


def rburp(s):
    """ (str) -> str. Reverse a string and remove the spaces from it. """
    return burp(r(s," "))


def r(s,splitby=None):
    """ (str or list[, split character]) -> str. Reverse a list or string.
    NOTE: if passed a list, it will be reversed in the calling scope.
    """
    s = s if type(s)==type([]) else list(s)
    s.reverse()
    return ''.join(s)


def two(integer,bitcount=None,bytecount=None):
    """ (positive integer, bit-width or byte-width) -> integer.
    Compute two's complement of an unsigned integer, based off a bit-width
    or byte-width. """
    # setup:
    if integer<0:
        raise ValueError("Can't compute two's complement on a negative number.")
    elif integer==0:
        return integer
    if bytecount and bitcount:
        raise ValueError("Pass either bytecount or bitcount, not both.")
    elif bytecount:
        bitcount = int(bytecount * 8)
    if (integer>>bitcount) > 0:
        raise ValueError("Specified bitcount too small to represent integer.")
    # ^ above, shifting by bitcount should completely zero the integer, if it
    # ^.. does not, it means the integer has more binary digits than the count
    # ^.. given
    # :setup
    sa = bitcount - 1 # compute shift-amount
    return (integer&((1<<sa)-1)) - ((integer>>sa)<<sa)
    # ^ above, subtract greatest digit from all lower digits.
    # ^.. For lesser digits, mask out the topmost digit using bitwise AND
    # ^.. For greatest digit, perform two bitshifts to get the form
    # ^.. "X0000..." where X is the greatest digit and 0 now holds the place
    # ^.. of all lesser digits.


def dnumerate(dic):
    """ -> generator. Analog of the `enumerate` keyword but for dictionaries """
    return ( (x,y) for x,y in zip(dic.keys(),dic.values()) )


def shout(s):
    """ (string) -> None. For testing: output stuff to console obviously. """
    pad = ' '*((60 - len(s)) // 2)
    print pad+"--------- "+s.upper()+" ---------"+pad


def papertap(bookmarks):
    """ array bookmark dictionaries -> None. Fix 'factor-16' issue if present.

    Occasionally, bookmark-times are off by a factor of 16. This
    function corrects this, assuming bookmarks are still in the order found
    in the .wbm-file.

    ...Since they're saved in ascending order in a .wbm, the issue is easy to
    detect and correct (unless the first bookmark is off by this factor, of
    course). If you find this is the case, try get_bookmarks() again with the
    `shiftHackFirst`-option."""
    previous = bookmarks[0]
    for v in bookmarks[1:]:
        if v["framepos"] < previous["framepos"]:
            v["framepos"] *= 16
            print "FIXED:",v["name"]
        previous = v


def ebasename(name):
    """ Get the basename from a path minus the basename's extension (if any)."""
    return os.path.splitext( os.path.basename(name) )[0]


def ext(path):
    """ Get the file-extension from a path."""
    return os.path.splitext(path)[1]


def as_tuples(spans,lastFrameNumber):
    """ (iterable of either tuples or bookmark-dicts) -> tuple.

Returned tuple contains:
    [0]: list/iterable of tuples:
        (startFrame, stopFrame, bookmark description, filename)
    [1]: boolean:
        Describes whether tuples had bookmark-descriptions associated with them
        
    """
    descriptionsProvided = False # assume false for now.
    if type(spans[0])==type((0,0)):
    # if spans is a container of tuples:
        if len(spans[0])>=3: descriptionsProvided = True
        return spans,descriptionsProvided
    else:
    # if spans is a container of bookmark-dictionaries:
        if "name" in spans[0].keys(): descriptionsProvided = True
    # Otherwise, spans is assumed to be a container of bookmark-dictionaries:
    tuples = []
    for x in range(len(spans[:-1])):
        tuples.append( (spans[x]["framepos"],
                        spans[x+1]["framepos"],
                        spans[x]["name"],
                        spans[x]["fn"]) )
    tuples.append( (spans[-1]["framepos"],
                    lastFrameNumber,
                    spans[-1]["name"],
                    spans[-1]["fn"]) )
    return tuples, descriptionsProvided


def get_filename_generator(fileCount,source="",dest="",sourceExt=True,
                           useExt=False,middlefix="_part_"):
    """ -> generator object for filenames according to parameters.

    If splitting a file up into multiple pieces, this function can be used
    to make naming all of those pieces easier.

source      --  String. Optional. Recommended if `dest` argument is not passed.
                Path to a source of data. (Or simply a filename if file is
                in cwd or search-path).

dest        --  Optional. String. Leading part of the name for the
                destination-files which this function will write to disk.
                Can be either a destination-directory, or a filename
                e.g. "output.wav"
                
                Note that generated names will have a suffix appended, so the
                actual output given dest="output.wav" would be something like
                "output_part_01.wav", "output_part_02.wav", etc.

                Similarly, if no dest is provided, output filenames will look
                like "sourcefile_part_01.wav", "sourcefile_part_02.wav", etc.

sourceExt   --  Optional. Bool. Whether to use the same extension as that of
                `source` file.
                
                If set false with useExt also false, `dest`'s extension is used.
                If set true with `useExt` false, `source`'s extension is used.
                If useExt is set true, this setting is ignored.

                Extensions with a leading '.' will not have another added, so
                system will append multiple dots only if multiple '.'s appear
                in the argument itself.

                Extensions /without/ a leading '.' will have one added.

useExt      --  Optional. Mixed. File-extension override for output filenames.
                It is recommended that callers provide this if both `source` and
                `dest` are empty or falsey.
                
                If set false: no override will occur.
                If set None: the empty string "" will be used as the extension.
                If string: `source`/`dest` extensions are ignored and this
                extension is used (it can be the empty string "") if no
                extension is desired whatsoever.

middlefix   --  Optional. String. Component to append between the initial
                filename and the numeric suffix and file-extension (if any).
    """
    if source and not os.path.isfile(source):
        raise ValueError("No valid source-file provided.")
    destIsDir = os.path.isdir(dest)
    destDir = ""
    destEfn = ""
    destExt = ""
    extOverride = (type(useExt)==type("")) or (useExt is None)
    useExt = "" if useExt==None else useExt
    useExt = '.' + useExt if (not useExt.startswith('.')) and useExt else useExt
    # ^ only add a '.' to the beginning of useExt if it's nonempty.
    if dest and not destIsDir:
        destDir = os.path.dirname(dest)
        destEfn = ebasename(dest)
        destExt = ext(dest) if not sourceExt else ext(source)
        # ^ overridden if extOverride
    elif dest and destIsDir:
        if (not useExt) and (not sourceExt):
            raise ValueError("useExt & sourceExt set False but dest is folder.")
        destDir = dest
        destEfn = ebasename(source)        
        destExt = ext(source)
        # ^ overridden if extOverride
    else:
    # if `dest` not provided:
        if (not useExt) and (not sourceExt):
            raise ValueError("useExt & sourceExt set False but dest not given.")
        destEfn = ebasename(source)
        destDir = os.path.dirname(source)
        destExt = ext(source)
        # ^ overridden if extOverride
    if extOverride: destExt = useExt
    numberFormat = "{:0>" + str(int(ceil(log10(fileCount)))) + "}"
    destBase = os.path.join(destDir,destEfn) +middlefix+ numberFormat + destExt
    for x in range(0,fileCount):
        yield destBase.format(x)


def copy_pieces(spans,source="",dest="", sourceExt=True, useExt=False,
                middlefix="_part_", fnGen=None):
    """ Copy one or more spans from a .wav-file to one or more other files.
    -> list.
    
    If spans are passed as an iterable of bookmark-dictionaries or if tuples
    provide descriptions at [2], returns toc-list will contain a mapping
    between bookmark names/descriptions and the files which were output.
    If tuples are only of length 2, returned list will be empty.

    Tip: if copying spans from a number of files, you can create a generator
    separately for all those spans and keep passing it in as `fnGen`, that way
    your naming-and-numbering scheme will remain consistent despite multiple
    calls to copy_pieces() on multiple files.

spans       --  Iterable. Container of tuples or bookmark-dictionaries.

                Tuples take the form:
                (startFrame,stopFrame[,description[,sourcefile]])

                Bookmark-dictionaries take the form described by next_mark().

source      --  Optional if `spans` is bookmark-dictionaries not tuples. String.
                Path to source-file from which pieces of audio will be copied.

                Defaults to: the value of ["fn"] from the first dict in `spans`

dest        --  Optional. String. Parameter to get_filename_generator().
                Ignored if providing own `fnGen`

sourceExt   --  Optional. Bool. Parameter to get_filename_generator().
                Ignored if providing own `fnGen`

useExt       -- Optional. Mixed. Parameter to get_filename_generator().
                Ignored if providing own `fnGen`

middlefix   --  Optional. String. Parameter to get_filename_generator().
                Ignored if providing own `fnGen`

fnGen       --  Optional. Generator. A generator-object (or similar) which will
                provide file-names for each span on every call of next() on the
                object. If passing a value for this option, make sure generator
                will yield enough names for all items in `spans` before it
                raises a StopIteration.

                Defaults to: generator returned by get_filename_generator()

    """
    # setup:
    justTuples = True # whether caller passed tuples vs. bookmark-dictionaries
    # ^ just intialized here, checked later.
    toc = []
    tuples = spans # overridden next if incorrect.
    if not source:
        if type(spans[0])==type((0,0)):
        # if caller provided tuples and no explicit source-filename:
            if not len(spans[0])>=4:
            # if caller did not provide a filename using the tuples:
                raise ValueError("No source filename provided. Provide one:\n"
                                 + " 1. expicit `source` keyword-arg with "
                                 + " filename/path \n"
                                 + " 2. `spans` as bookmark-dictionaries with"
                                 + " ['fn']-values pointing to accessible files"
                                 + " (full paths or proper os.path or cwd set)"
                                 + " \n"
                                 + " 3. `spans` as tuples with filename at [2]."
                                )
            source = spans[0][3]
        elif type(spans[0])==type({}):
        # if caller provided bookmark-dictionaries but no explicit source-filename:
            source = spans[0]["fn"]
        else:
        # if caller provided an iterable of something entirely else:
            raise TypeError("`spans` should be iterable of dicts or tuples.")
    rhandle = WaveReadWrapper(source)
    framecount = rhandle.getnframes()
    tuples,descriptionsGiven = as_tuples(spans,framecount)
    if not fnGen: fnGen = get_filename_generator( len(spans),source,dest,
                                                  sourceExt,useExt,middlefix )

    # :setup
    for x,t in enumerate(tuples):
        rhandle.setpos(t[0])
        data = rhandle.readframes(t[1] - t[0])
        outputName = fnGen.next()
        if descriptionsGiven: toc.append('{}\t"{}"'.format(outputName,t[2]))
        whandle = wave.open(outputName,'wb')
        whandle.setparams( rhandle.getparams() )
        whandle.writeframes( data )
        whandle.close()
    print "Completed copying segments of {}".format(source)
    return toc
