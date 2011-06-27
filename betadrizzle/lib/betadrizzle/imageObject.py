#!/usr/bin/env python
"""
A class which makes image objects for 
each input filename

"""
from __future__ import division # confidence medium

import sys,types,copy,os,re
from stsci.tools import fileutil
import pyfits
import util,wcs_functions
import buildmask
import numpy as np

IRAF_DTYPES={'float64':-64,'float32':-32,'uint8':8,'int16':16,'int32':32}

__version__ = '0.1dev1'

class baseImageObject:
    """ base ImageObject which defines the primary set of methods """
    def __init__(self,filename):

        self.scienceExt= "SCI" # the extension the science image is stored in
        self.maskExt="DQ" #the extension with the mask image in it
        self.errExt = "ERR"  # the extension the ERR array can be found in
        self._filename = filename
        self.native_units='ELECTRONS'

        self.flatkey = None  # keyword which points to flat-field reference file
        
        self._image = None
        self._instrument=None
        self._rootname=None
        self.outputNames={}
        self.outputValues = {}
        self.createContext = True
         
        #this is the number of science chips to be processed in the file
        self._numchips=1
        self._nextend=0
        # this is the number of chip which will be combined based on 'group' parameter
        self._nmembers = 0

    def __getitem__(self,exten):
        """overload  getitem to return the data and header
            these only work on the HDU list already in memory
            once the data has been zero's in self._image you should
            use getData or getHeader to re-read the file
        """
        return fileutil.getExtn(self._image,extn=exten)
    
    
    def __cmp__(self, other):
        """overload the comparison operator
            just to check the filename of the object?
         """
        if isinstance(other,imageObject):
            if (self._filename == other._filename):
                return True            
        return False

    def _isNotValid(self, par1, par2):
        """ Method used to determine if a value or keyword is supplied as 
            input for instrument specific parameters.
        """
        invalidValues = [None,'None','INDEF','']
        if (par1 in invalidValues) and (par2 in invalidValues):
            return True
        else:
            return False
    
    def info(self):
        """return fits information on the _image"""
        #if the file hasn't been closed yet then we can
        #use the pyfits info which looks at the extensions
        #if(self._isSimpleFits):
        #    print self._filename," is a simple fits image"
        #else:
        self._image.info()    
 
    def close(self):
        """close the object nicely
           and release all the data arrays from memory
           YOU CANT GET IT BACK, the pointers and data are gone
           so use the getData method to get the data array
           returned for future use. You can use putData to 
           reattach a new data array to the imageObject
        """
        self._image.close()  #calls pyfits.close()
        
        #we actuallly want to make sure that all the
        #data extensions have been closed and deleted
        #since we could have the DQ,ERR and others read in
        #at this point, but I'd like there to be something
        #valid there afterwards that I can play with
        
        if not self._isSimpleFits: 
            for ext,hdu in enumerate(self._image):
                #use the datatype for the extension
                dtype=self.getNumpyType(hdu.header["BITPIX"])
                hdu.data = None #np.array(0,dtype=dtype)  #so we dont get io errors on stuff that wasn't read in yet     
        else:            
            self._image.data= None # np.array(0,dtype=self.getNumpyType(self._image.header["BITPIX"]))
            
    def clean(self):
        """ Deletes intermediate products generated for this imageObject
        """
        clean_files = ['blotImage','crcorImage','crmaskImage','finalMask','staticMask','singleDrizMask',
                        'outSky','outSContext','outSWeight','outSingle','outMedian','d2imfile','dqmask']
        print 'Removing intermediate files for ',self._filename
        # We need to remove the combined products first; namely, median image
        util.removeFileSafely(self.outputNames['outMedian'])
        # Now remove chip-specific intermediate files, if any were created.
        for chip in self.returnAllChips(extname='SCI'):
            for fname in clean_files:
                if chip.outputNames.has_key(fname):
                    util.removeFileSafely(chip.outputNames[fname])
            
    def getData(self,exten=None):
        """return just the data array from the specified extension 
        
            fileutil is used instead of pyfits to account for
            non FITS input images. openImage returns a pyfits object
        
        """
        if exten.lower().find('sci') > -1:
            # For SCI extensions, the current file will have the data
            fname = self._filename
        else:
            # otherwise, the data being requested may need to come from a 
            # separate file, as is the case with WFPC2 DQ data.
            #
            # convert exten to 'sci',extver to get the DQ info for that chip
            extn = exten.split(',')
            sci_chip = self._image[self.scienceExt,int(extn[1])]
            fname = sci_chip.dqfile
        extnum = self._interpretExten(exten)
        if self._image[extnum].data is None:
            if os.path.exists(fname):
                _image=fileutil.openImage(fname,clobber=False,memmap=0)
                _data=fileutil.getExtn(_image,extn=exten).data
                _image.close()
                del _image
            else: 
                _data = None
        else:
            _data = self._image[extnum].data
        return _data

    def getHeader(self,exten=None):
        """return just the specified header extension
           
        fileutil is used instead of pyfits to account for
        non FITS input images. openImage returns a pyfits object        
        """
        _image=fileutil.openImage(self._filename,clobber=False,memmap=0)
        _header=fileutil.getExtn(_image,extn=exten).header
        _image.close()
        del _image
        return _header

    def _interpretExten(self,exten):
        #check if the exten is a string or number and translate to the correct chip
        _extnum=0
        
        if ',' in str(exten): #assume a string like "sci,1" has been given
            _extensplit=exten.split(',')
            _extname=_extensplit[0]
            _extver=int(_extensplit[1])
            _extnum=self.findExtNum(_extname,_extver)
        else:
            #assume that a direct extnum has been given    
            _extnum=int(exten)
            
        if(_extnum == None):
            print "no extension number found"
            return ValueError

        return _extnum
    
    def updateData(self,exten,data):
        """ Write out updated data and header 
            to the original input file for this object.
        """
        _extnum=self._interpretExten(exten)
        fimg = fileutil.openImage(self._filename,mode='update')
        fimg[_extnum].data = data
        fimg[_extnum].header = self._image[_extnum].header
        fimg.close()

    def putData(self,data=None,exten=None):
        """Now that we are removing the data from the object to save memory,
            we need something that cleanly puts the data array back into
            the object so that we can write out everything together  using
            something like pyfits.writeto....this method is an attempt to
            make sure that when you add an array back to the .data section
            of the hdu it still matches the header information for that
            section ( ie. update the bitpix to reflect the datatype of the
            array you are adding). The other header stuff is  up to you to verify...
            
            data should be the data array
            exten is where you want to stick it, either extension number or
                a string like 'sci,1'
        """
        if (data == None):
            print "No data supplied"
        else:           
            _extnum=_interpretExten(exten)
                                    
            #update the bitpix to the current datatype, this aint fancy and ignores bscale
            self._image[_extnum].header["BITPIX"]=IRAF_DTYPES[data.dtype.name]
            self._image[_extnum].data=data

    def getAllData(self,extname=None,exclude=None):
        """ this function is meant to make it easier to attach ALL the data
        extensions of the image object so that we can write out copies of the
        original image nicer.
        
        if no extname is given, the it retrieves all data from the original
        file and attaches it. Otherwise, give the name of the extensions
        you want and all of those will be restored.
        
        ok, I added another option. If you want to get all the data
        extensions EXCEPT a particular one, leave extname=NONE and
        set exclude=EXTNAME. This is helpfull cause you might not know
        all the extnames the image has, this will find out and exclude
        the one you do not want overwritten.
        """
        
        extensions = self._findExtnames(extname=extname,exclude=exclude)
                   
        for i in range(1,self._nextend+1,1):
            if self._image[i].__dict__.has_key('_xtn') and "IMAGE" in self._image[i]._xtn:
                extver = self._image[i].header['extver']
                if (self._image[i].extname in extensions) and self._image[self.scienceExt,extver].group_member:
                    self._image[i].data=self.getData(self._image[i].extname + ','+str(self._image[i].extver))

    def returnAllChips(self,extname=None,exclude=None):
        """ Returns a list containing all the chips which match the extname given
            minus those specified for exclusion (if any). 
        """
        extensions = self._findExtnames(extname=extname,exclude=exclude)
        chiplist = []
        for i in range(1,self._nextend+1,1):
            if self._image[i].header.has_key('extver'):
                extver = self._image[i].header['extver']
            else:
                extver = 1
            if self._image[i].__dict__.has_key('_xtn') and "IMAGE" in self._image[i]._xtn:
                if (self._image[i].extname in extensions) and self._image[self.scienceExt,extver].group_member:
                    chiplist.append(self._image[i])
        return chiplist

    def _findExtnames(self,extname=None,exclude=None):
        """ This method builds a list of all extensions which have 'EXTNAME'==extname
            and do not include any extensions with 'EXTNAME'==exclude, if any are 
            specified for exclusion at all.
        """
        #make a list of the available extension names for the object
        extensions=[]
        if extname != None:
            if not isinstance(extname,list): extname=[extname]
            for extn in extname:
                extensions.append(extn.upper())
        else:
        #restore all the extensions data from the original file, be careful here
        #if you've altered data in memory you want to keep!
            for i in range(1,self._nextend+1,1):
                if self._image[i].__dict__.has_key('_xtn') and "IMAGE" in self._image[i]._xtn:
                    if self._image[i].extname.upper() not in extensions:
                        extensions.append(self._image[i].extname)
        #remove this extension from the list
        if exclude != None:
            exclude.upper()
            if exclude in extensions:
                newExt=[]
                for item in extensions:
                    if item != exclude:
                        newExt.append(item)
            extensions=newExt
            del newExt
        return extensions
    
    def findExtNum(self,extname=None,extver=1):
        """find the extension number of the give extname and extver"""      
        extnum=None
        _extname=extname.upper()
         
        if not self._isSimpleFits:
            for ext in range(1,self._nextend+1,1):
                if self._image[ext].__dict__.has_key('_xtn') and \
                "IMAGE" in self._image[ext]._xtn and \
                (self._image[ext].extname == _extname):
                    if (self._image[ext].extver == extver):
                        extnum=self._image[ext].extnum
        else:
            print "Image is simple fits"
            
        return extnum        
        
    def _assignRootname(self, chip):
        """assign a unique rootname for the image based in the expname"""
        
        extname=self._image[self.scienceExt,chip].header["EXTNAME"].lower()
        extver=self._image[self.scienceExt,chip].header["EXTVER"]
        expname=self._image[self.scienceExt,chip].header["EXPNAME"].lower()
    
        # record extension-based name to reflect what extension a mask file corresponds to
        self._image[self.scienceExt,chip].rootname=expname + "_" + extname + str(extver)
        self._image[self.scienceExt,chip].sciname=self._filename + "[" + extname +","+str(extver)+"]"
        self._image[self.scienceExt,chip].dqrootname=self._rootname + "_" + extname + str(extver)
        # Needed to keep EXPNAMEs associated properly (1 EXPNAME for all chips)
        self._image[self.scienceExt,chip]._expname=expname
        self._image[self.scienceExt,chip]._chip =chip
        

    def _setOutputNames(self,rootname):
        """
        Define the default output filenames for drizzle products,
        these are based on the original rootname of the image 

        filename should be just 1 filename, so call this in a loop
        for chip names contained inside a file

        """
        # Define FITS output filenames for intermediate products
        
        # Build names based on final DRIZZLE output name
        # where 'output' normally would have been created 
        #   by 'process_input()'
        #

        outFinal = rootname+'_drz.fits'
        outSci = rootname+'_drz_sci.fits'
        outWeight = rootname+'_drz_weight.fits'
        outContext = rootname+'_drz_context.fits'
        outMedian = rootname+'_med.fits'
                
        # Build names based on input name
        indx = self._filename.find('.fits')
        origFilename = self._filename[:indx]+'_OrIg.fits'
        outSky = rootname + '_sky.fits'
        outSingle = rootname+'_single_sci.fits'
        outSWeight = rootname+'_single_wht.fits'
        
        # Build outputNames dictionary
        fnames={
            'origFilename':origFilename,
            'outFinal':outFinal,
            'outMedian':outMedian,
            'outSci':outSci,
            'outWeight':outWeight,
            'outContext':outContext,
            'outSingle':outSingle,
            'outSWeight':outSWeight,
            'outSContext':None,
            'outSky':outSky,
            'ivmFile':None}
        

        return fnames

    def _setChipOutputNames(self,rootname,chip):
        blotImage = rootname + '_blt.fits'
        crmaskImage = rootname + '_crmask.fits'
        crcorImage = rootname + '_cor.fits'


        # Start with global names
        fnames = self.outputNames

        # Now add chip-specific entries
        fnames['blotImage'] = blotImage
        fnames['crcorImage'] = crcorImage
        fnames['crmaskImage'] = crmaskImage
        sci_chip = self._image[self.scienceExt,chip]
        # Define mask names as additional entries into outputNames dictionary
        fnames['finalMask']=sci_chip.dqrootname+'_final_mask.fits' # used by final_drizzle
        fnames['singleDrizMask']=fnames['finalMask'].replace('final','single')
        fnames['staticMask']=None
        
        # Add the following entries for use in creating outputImage object
        fnames['data'] = sci_chip.sciname
        return fnames

    def updateOutputValues(self,output_wcs):
        """Copy info from output WCSObject into outputnames for each chip
           for use in creating outputimage object. 
        """
        
        outputvals = self.outputValues
        
        outputvals['output'] = output_wcs.outputNames['outFinal']
        outputvals['outnx'] = output_wcs.wcs.naxis1
        outputvals['outny'] = output_wcs.wcs.naxis2
        outputvals['texptime'] = output_wcs._exptime
        outputvals['texpstart'] = output_wcs._expstart
        outputvals['texpend'] = output_wcs._expend
        outputvals['nimages'] = output_wcs.nimages

        outputvals['scale'] = output_wcs.wcs.pscale #/ self._image[self.scienceExt,1].wcs.pscale
        outputvals['exptime'] = self._exptime
        
        outnames = self.outputNames
        outnames['outMedian'] = output_wcs.outputNames['outMedian']
        outnames['outFinal'] = output_wcs.outputNames['outFinal']
        outnames['outSci'] = output_wcs.outputNames['outSci']
        outnames['outWeight'] = output_wcs.outputNames['outWeight']
        outnames['outContext'] = output_wcs.outputNames['outContext']
        
    def updateContextImage(self,contextpar):
        """ Reset the name of the context image to None if parameter `context`== False
        """
        self.createContext = contextpar
        if contextpar == False:
            print 'No context image will be created for ',self._filename
            self.outputNames['outContext'] = None
        
    def find_DQ_extension(self):
        ''' Return the suffix for the data quality extension and the name of the file
            which that DQ extension should be read from.
        '''
        dqfile = None
        dq_suffix=None
        if(self.maskExt != None):
            for hdu in self._image:
                # Look for DQ extension in input file
                if hdu.header.has_key('extname') and hdu.header['extname'].lower() == self.maskExt.lower():
                    dqfile = self._filename
                    dq_suffix=self.maskExt
                    break

        return dqfile,dq_suffix
            
    
    def getKeywordList(self,kw):
        """return lists of all attribute values 
           for all active chips in the imageObject
        """
        kwlist = []
        for chip in range(1,self._numchips+1,1):
            sci_chip = self._image[self.scienceExt,chip]
            if sci_chip.group_member:
                kwlist.append(sci_chip.__dict__[kw])
            
        return kwlist

    def getGain(self,exten):
        return self._image[exten]._gain

    def getflat(self,chip):
        """
        Method for retrieving a detector's flat field.
        
        Returns
        -------
        flat: array
            This method will return an array the same shape as the image in **units of electrons**.
        
        """
        sci_chip = self._image[self.scienceExt,chip]
        exten = '%s,%d'%(self.errExt,chip)
        # The keyword for ACS flat fields in the primary header of the flt
        # file is pfltfile.  This flat file is already in the required 
        # units of electrons.
        
        # The use of fileutil.osfn interprets any environment variable, such as jref$,
        # used in the specification of the reference filename
        filename = fileutil.osfn(self._image["PRIMARY"].header[self.flatkey])
        
        try:
            handle = fileutil.openImage(filename,mode='readonly',memmap=0)
            hdu = fileutil.getExtn(handle,extn=exten)
            data = hdu.data[sci_chip.ltv2:sci_chip.size2,sci_chip.ltv1:sci_chip.size1]
            handle.close()
        except:
            data = np.ones(sci_chip.image_shape,dtype=sci_chip.image_dtype)
            str = "Cannot find file "+filename+".\n    Treating flatfield constant value of '1'.\n"
            print str
        flat = data
        return flat

    def getReadNoiseImage(self,chip):
        """
        
        Purpose
        =======
        Method for returning the readnoise image of a detector 
        (in electrons).  
        
        The method will return an array of the same shape as the image.
        
        :units: electrons
        
        """
        sci_chip = self._image[self.scienceExt,chip]
        
        return np.ones(sci_chip.image_shape,dtype=sci_chip.image_dtype) * sci_chip._rdnoise

    def getdarkimg(self,chip):
        """
        
        Purpose
        =======
        Return an array representing the dark image for the detector.
        
        :units: electrons
        
        """
        sci_chip = self._image[self.scienceExt,chip]
        return np.ones(sci_chip.image_shape,dtype=sci_chip.image_dtype)*sci_chip.darkcurrent
    
    def getskyimg(self,chip):
        """
        
        Purpose
        =======
        Return an array representing the sky image for the detector.  The value
        of the sky is what would actually be subtracted from the exposure by
        the skysub step.
        
        :units: electrons
        
        """
        sci_chip = self._image[self.scienceExt,chip]
        return np.ones(sci_chip.image_shape,dtype=sci_chip.image_dtype)*sci_chip.subtractedSky

    def getdarkcurrent(self):
        """
        
        Purpose
        =======
        Return the dark current for the detector.  This value
        will be contained within an instrument specific keyword.
        The value in the image header will be converted to units
        of electrons.
        
        :units: electrons
        
        """
        pass
    
#the following two functions are basically doing the same thing,
#how are they used differently in the code?                
    def getExtensions(self,extname='SCI',section=None):
        ''' Return the list of EXTVER values for extensions with name specified in extname.
        '''
        if section == None:
            numext = 0
            section = []
            for hdu in self._image:
               if hdu.header.has_key('extname') and hdu.header['extname'] == extname:
                    section.append(hdu.header['extver'])
        else:
            if not isinstance(section,list):
                section = [section]

        return section
        
        
         
    def _countEXT(self,extname="SCI"):

        """
            count the number of extensions in the file
            with the given name (EXTNAME)
        """
        count=0 #simple fits image

        if (self._image['PRIMARY'].header["EXTEND"]):
            for i,hdu in enumerate(self._image):
                if i > 0:                
                    hduExtname = False  
                    if hdu.header.has_key('EXTNAME'):  
                        self._image[i].extnum=i
                        self._image[i].extname=hdu.header["EXTNAME"]
                        hduExtname = True
                    if hdu.header.has_key('EXTVER'):
                        self._image[i].extver=hdu.header["EXTVER"]
                    else:
                        self._image[i].extver = 1
                        
                    if ((extname is not None) and \
                            (hduExtname and (hdu.header["EXTNAME"] == extname))) \
                            or extname is None:
                        count=count+1    
        return count
    
    def getNumpyType(self,irafType):
        """return the corresponding numpy data type"""
        
        iraf={-64:'float64',-32:'float32',8:'uint8',16:'int16',32:'int32'}
        
        return iraf[irafType]
        
    def buildMask(self,chip,bits=0,write=False):
        """ 
        Build masks as specified in the user parameters found in the 
        configObj object.
            
        we should overload this function in the instrument specific
        implementations so that we can add other stuff to the badpixel
        mask? Like vignetting areas and chip boundries in nicmos which
        are camera dependent? these are not defined in the DQ masks, but
        should be masked out to get the best results in multidrizzle
        """
        dqarr = self.getData(exten=self.maskExt+','+str(chip))
        dqmask = buildmask.buildMask(dqarr,bits)
            
        if write:
            phdu = pyfits.PrimaryHDU(data=dqmask,header=self._image[self.maskExt,chip].header)
            dqmask_name = self._image[self.scienceExt,chip].dqrootname+'_dqmask.fits'
            print 'Writing out DQ/weight mask: ',dqmask_name
            if os.path.exists(dqmask_name): os.remove(dqmask_name)
            phdu.writeto(dqmask_name)
            del phdu
            self._image[self.scienceExt,chip].dqmaskname = dqmask_name
            # record the name of this mask file that was created for later 
            # removal by the 'clean()' method
            self._image[self.scienceExt,chip].outputnames['dqmask'] = dqmask_name
            
        del dqarr            
        return dqmask

    def buildIVMmask(self,chip,dqarr,scale):
        """ Builds a weight mask from an input DQ array and either an IVM array
        provided by the user or a self-generated IVM array derived from the 
        flat-field reference file associated with the input image.
        """
        sci_chip = self._image[self.scienceExt,chip]
        ivmname = self.outputNames['ivmFile']

        if ivmname != None:
            print "Applying user supplied IVM files for chip ",chip
            #Parse the input file name to get the extension we are working on
            extn = "IVM,"+chip
            
            #Open the mask image for updating and the IVM image
            ivm =  fileutil.openImage(ivmname,mode='readonly')
            ivmfile = fileutil.getExtn(ivm,extn)
            
            # Multiply the IVM file by the input mask in place.        
            ivmarr = ivmfile.data * dqarr
            
            ivm.close()

        else:
                        
            print "Automatically creating IVM files for chip ",chip
            # If no IVM files were provided by the user we will 
            # need to automatically generate them based upon 
            # instrument specific information.
            
            flat = self.getflat(chip)
            RN = self.getReadNoiseImage(chip)
            darkimg = self.getdarkimg(chip)
            skyimg = self.getskyimg(chip)
            
            ivm = (flat)**2/(darkimg+(skyimg*flat)+RN**2)
            
            # Multiply the IVM file by the input mask in place.        
            ivmarr = ivm * dqarr
            
        # Update 'wt_scl' parameter to match use of IVM file
        sci_chip._wtscl = pow(sci_chip._exptime,2)/pow(scale,4)

        return ivmarr.astype(np.float32)
        
    def buildERRmask(self,chip,dqarr,scale):
        """ Builds a weight mask from an input DQ array and an ERR array
        associated with the input image.
        """
        sci_chip = self._image[self.scienceExt,chip]  
        
        # Set default value in case of error, or lack of ERR array
        errmask = dqarr

        if self.errExt is not None:
            try:
                # Attempt to open the ERR image.
                err = self.getData(exten=self.errExt+','+str(chip))

                print "Applying ERR weighting to DQ mask for chip ",chip

                # Multiply the scaled ERR file by the input mask in place.        
                errmask = 1/(err)**2 * dqarr

                # Update 'wt_scl' parameter to match use of IVM file
                sci_chip._wtscl = pow(sci_chip._exptime,2)/pow(scale,4)

                del err

            except:
            # We cannot find an 'ERR' extension and the data isn't WFPC2.  Print a generic warning message
            # and continue on with the final drizzle step.
                generrstr =  "*******************************************\n"
                generrstr += "*                                         *\n"
                generrstr += "* WARNING: No ERR weighting will be       *\n"
                generrstr += "* applied to the mask used in the final   *\n"
                generrstr += "* drizzle step!  Weighting will be only   *\n"
                generrstr += "* by exposure time.                       *\n"
                generrstr += "*                                         *\n"
                generrstr += "* The data provided as input does not     *\n"
                generrstr += "* contain an ERR extension.               *\n"
                generrstr += "*                                         *\n"
                generrstr =  "*******************************************\n"
                print generrstr
                print "\n Continue with final drizzle step..."
        else:
        # If we were unable to find an 'ERR' extension to apply, one possible reason was that
        # the input was a 'standard' WFPC2 data file that does not actually contain an error array.
        # Test for this condition and issue a Warning to the user and continue on to the final
        # drizzle.   
            errstr =  "*******************************************\n"
            errstr += "*                                         *\n"
            errstr += "* WARNING: No ERR weighting will be       *\n"
            errstr += "* applied to the mask used in the final   *\n"
            errstr += "* drizzle step!  Weighting will be only   *\n"
            errstr += "* by exposure time.                       *\n"
            errstr += "*                                         *\n"
            errstr += "* The WFPC2 data provided as input does   *\n"
            errstr += "* not contain ERR arrays.  WFPC2 data is  *\n"
            errstr += "* not supported by this weighting type.   *\n"
            errstr += "*                                         *\n"
            errstr += "* A workaround would be to create inverse *\n"
            errstr += "* variance maps and use 'IVM' as the      *\n"
            errstr += "* final_wht_type.  See the HELP file for  *\n"
            errstr += "* more details on using inverse variance  *\n"
            errstr += "* maps.                                   *\n" 
            errstr += "*                                         *\n"
            errstr =  "*******************************************\n"
            print errstr
            print "\n Continue with final drizzle step..."

        return errmask.astype(np.float32)

    def updateIVMName(self,ivmname):
        """ Update outputNames for image with user-supplied IVM filename."""
        self.outputNames['ivmFile'] = ivmname

    def set_mt_wcs(self,image):
        """ Reset the WCS for this image based on the WCS information from 
        another imageObject.
        """
        for chip in range(1,self._numchips+1,1):
            sci_chip = self._image[self.scienceExt,chip]
            ref_chip = image._image[image.scienceExt,chip]
            # Do we want to keep track of original WCS or not? No reason now...
            sci_chip.wcs = ref_chip.wcs.copy()
            
    def set_wtscl(self,chip,wtscl_par):
        """ Sets the value of the wt_scl parameter as needed for drizzling
        """
        sci_chip = self._image[self.scienceExt,chip]

        exptime = sci_chip._exptime
        if wtscl_par != None:
            if isinstance(wtscl_par,types.StringType):
                if  wtscl_par.isdigit() == False :
                    # String passed in as value, check for 'exptime' or 'expsq'
                    _wtscl_float = None
                    try:
                        _wtscl_float = float(wtscl_par)
                    except ValueError:
                        _wtscl_float = None
                    if _wtscl_float != None:
                        _wtscl = _wtscl_float
                    elif wtscl_par == 'expsq':
                        _wtscl = exptime*exptime
                    else:
                        # Default to the case of 'exptime', if
                        #   not explicitly specified as 'expsq'
                        _wtscl = exptime
                else:
                    # int value passed in as a string, convert to float
                    _wtscl = float(wtscl_par)
            else:
                # We have a non-string value passed in...
                _wtscl = float(wtscl_par)
        else:
            # Default case: wt_scl = exptime
            _wtscl = exptime
        
        sci_chip._wtscl = _wtscl
        
    def set_units(self):
        """ Record the units for this image, both BUNITS from header and 
            in_units as needed internally.
            This method will be defined specifically for each instrument.
        """
        pass
        
    def getInstrParameter(self, value, header, keyword):
        """ This method gets a instrument parameter from a
            pair of task parameters: a value, and a header keyword.

            The default behavior is:
              - if the value and header keyword are given, raise an exception.
              - if the value is given, use it.
              - if the value is blank and the header keyword is given, use
                the header keyword.
              - if both are blank, or if the header keyword is not
                found, return None.
        """
        if (value != None and value != '')  and (keyword != None and keyword.strip() != ''):
            exceptionMessage = "ERROR: Your input is ambiguous!  Please specify either a value or a keyword.\n  You specifed both " + str(value) + " and " + str(keyword) 
            raise ValueError, exceptionMessage
        elif value != None and value != '':
            return self._averageFromList(value)
        elif keyword != None and keyword.strip() != '':
            return self._averageFromHeader(header, keyword)
        else:
            return None

    def _averageFromHeader(self, header, keyword):
        """ Averages out values taken from header. The keywords where
            to read values from are passed as a comma-separated list.
        """
        _list = ''
        for _kw in keyword.split(','):
            if header.has_key(_kw):
                _list = _list + ',' + str(header[_kw])
            else:
                return None
        return self._averageFromList(_list)

    def _averageFromList(self, param):
        """ Averages out values passed as a comma-separated
            list, disregarding the zero-valued entries.
        """
        _result = 0.0
        _count = 0

        for _param in param.split(','):
            if _param != '' and float(_param) != 0.0:
                _result = _result + float(_param)
                _count  += 1

        if _count >= 1:
            _result = _result / _count
        return _result
        
class imageObject(baseImageObject):
    """
        This returns an imageObject that contains all the
        necessary information to run the image file through
        any multidrizzle function. It is essentially a 
        PyFits object with extra attributes
        
        There will be generic keywords which are good for
        the entire image file, and some that might pertain
        only to the specific chip. 
    
    """
    
    def __init__(self,filename,group=None):
        baseImageObject.__init__(self,filename)
        
        #filutil open returns a pyfits object
        try:
            self._image=fileutil.openImage(filename,clobber=False,memmap=0)
            
        except IOError:
            print "\nUnable to open file:",filename
            raise IOError

        #populate the global attributes which are good for all the chips in the file
        self._rootname=self._image['PRIMARY'].header["ROOTNAME"]
        self.outputNames=self._setOutputNames(self._rootname)
        
        #self._exptime=self._image["PRIMARY"].header["EXPTIME"]
        #exptime should be set in the image subclass code since it's kept in different places
#        if(self._exptime == 0): 
        self._exptime =1. #to avoid divide by zero
 #           print "Setting exposure time to 1. to avoid div/0!"
            
       #this is the number of science chips to be processed in the file
        self._numchips=self._countEXT(extname=self.scienceExt)

        self.proc_unit = None
        
        #self._nextend=self._image["PRIMARY"].header["NEXTEND"]
        self._nextend = self._countEXT(extname=None)
        
        if (self._numchips == 0):
            #the simple fits image contains the data in the primary extension,
            #this will help us deal with the rest of the code that looks
            #and acts on chips :)
            #self._nextend=1
            self._numchips=1
            self.scienceExt="PRIMARY"
            self.maskExt=None
            self._image["PRIMARY"].header.update("EXTNAME","PRIMARY")
            self._image["PRIMARY"].header.update("EXTVER",1)
            self._image["PRIMARY"].extnum=0
  
        self._isSimpleFits = False
        
        if group not in [None,'']:
            # Only use selected chip(s?)
            group_id = fileutil.parseExtn(str(group))
            if group_id[0] == '':
                # find extname/extver which corresponds to this extension number
                group_extname = self._image[group_id[1]].header['EXTNAME']
                group_extver = self._image[group_id[1]].header['EXTVER']
                self.group = [group_extname,group_extver]
            else:
                self.group = group_id
        else:
            # Use all chips
            self.group = None
            
        if not self._isSimpleFits:
            
            #assign chip specific information
            for chip in range(1,self._numchips+1,1):

                self._assignRootname(chip)
                sci_chip = self._image[self.scienceExt,chip]

                # Set a flag to indicate whether this chip should be included
                # or not, based on user input from the 'group' parameter.
                if self.group is None or (self.group is not None and self.group[1] == chip):
                    sci_chip.group_member = True
                    self._nmembers += 1
                else:
                    sci_chip.group_member = False

                sci_chip.signature = None

                sci_chip.dqname = None
                sci_chip.dqmaskname = None

                sci_chip.dqfile,sci_chip.dq_extn = self.find_DQ_extension()   
                #self.maskExt = sci_chip.dq_extn
                if(sci_chip.dqfile != None):            
                    sci_chip.dqname = sci_chip.dqfile +'['+sci_chip.dq_extn+','+str(chip)+']'
                    
                # build up HSTWCS object for each chip, which will be necessary for drizzling operations
                sci_chip.wcs=wcs_functions.get_hstwcs(self._filename,self._image,sci_chip.extnum)
                sci_chip.detnum,sci_chip.binned = util.get_detnum(sci_chip.wcs,self._filename,chip)

                #assuming all the chips don't have the same dimensions in the file
                sci_chip._naxis1=sci_chip.header["NAXIS1"]
                sci_chip._naxis2=sci_chip.header["NAXIS2"]            

                # record the exptime values for this chip so that it can be
                # easily used to generate the composite value for the final output image
                sci_chip._expstart,sci_chip._expend = util.get_expstart(sci_chip.header,self._image['PRIMARY'].header)
                            
                sci_chip.outputNames=self._setChipOutputNames(sci_chip.rootname,chip).copy() #this is a dictionary
                # Set the units: both bunit and in_units
                self.set_units(chip)
                
                #initialize gain, readnoise, and exptime attributes
                # the actual values will be set by each instrument based on 
                # keyword names specific to that instrument by 'setInstrumentParamters()'
                sci_chip._headergain = 1 # gain value read from header
                sci_chip._gain = 1.0     # calibrated gain value
                sci_chip._rdnoise = 1.0  # calibrated readnoise
                sci_chip._exptime = 1.0
                sci_chip._effGain = 1.0
                sci_chip._wtscl = 1.0
                
                # Keep track of the computed sky value for this chip
                sci_chip.computedSky = 0.0
                # Keep track of the sky value that was subtracted from this chip
                sci_chip.subtractedSky = 0.0
                sci_chip.darkcurrent = 0.0
                
                # The following attributes are used when working with sub-arrays
                # and get reference file arrays for auto-generation of IVM masks
                try:
                    sci_chip.ltv1 = sci_chip.header['LTV1'] * -1
                    sci_chip.ltv2 = sci_chip.header['LTV2'] * -1
                except KeyError:
                    sci_chip.ltv1 = 0
                    sci_chip.ltv2 = 0
                sci_chip.size1 = sci_chip.header['NAXIS1'] + sci_chip.ltv1
                sci_chip.size2 = sci_chip.header['NAXIS2'] + sci_chip.ltv2
                sci_chip.image_shape = (sci_chip.size2,sci_chip.size1)
                # Interpret the array dtype by translating the IRAF BITPIX value 
                for dtype in IRAF_DTYPES.keys():
                    if sci_chip.header['BITPIX'] == IRAF_DTYPES[dtype]:
                        sci_chip.image_dtype = dtype
                        break

        
    def setInstrumentParameters(self,instrpars):
        """ Define instrument-specific parameters for use in the code. 
            By definition, this definition will need to be overridden by 
            methods defined in each instrument's sub-class.
        """
        pass
                                    
    def set_units(self,chip):
        """ Define units for this image."""
        # Determine output value of BUNITS
        # and make sure it is not specified as 'ergs/cm...'
        sci_chip = self._image[self.scienceExt,chip]

        _bunit = None
        if sci_chip.header.has_key('BUNIT') and sci_chip.header['BUNIT'].find('ergs') < 0:
            _bunit = sci_chip.header['BUNIT']
        else:
            _bunit = 'ELECTRONS/S'
        sci_chip._bunit = _bunit
        #
        sci_chip.in_units = 'counts'
                            

class WCSObject(baseImageObject):
    def __init__(self,filename,suffix='_drz.fits'):
        baseImageObject.__init__(self,filename)
                
        self._image = pyfits.HDUList()
        self._image.append(pyfits.PrimaryHDU())
        
        # Build rootname, but guard against the rootname being given without
        # the '_drz.fits' suffix
        patt = re.compile(r"_drz\w*.fits$")
        m = patt.search(filename)
        if m:
            self._rootname = filename[:m.start()]
        else:
            # Guard against having .fits in the rootname
            indx = filename.find('.fits')
            if indx>0:
                self._rootname = filename[:indx]
            else:
                self._rootname = filename
            
        self.outputNames = self._setOutputNames(self._rootname)
        self.nimages = 1
    
        self._bunit = 'ELECTRONS/S'
        self.default_wcs = None
        self.final_wcs = None
        self.single_wcs = None

    def restore_wcs(self):
        self.wcs = copy.copy(self.default_wcs)
