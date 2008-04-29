from distutils.core import setup, Extension
from distutils import sysconfig
import sys

if not hasattr(sys, 'version_info') or sys.version_info < (2,3,0,'final', 0):
    raise SystemExit, "Python 2.3 or later required to build imagestats."
try:
    import numpy
    import numpy.numarray as nn
except:
    raise ImportError("Numarray was not found. It may not be installed or it may not be on your PYTHONPATH.\n")

if numpy.__version__ < "1.0.2":
    raise SystemExit, "Numpy 1.0.2 or later required to build imagemanip."

if sys.platform != 'win32':
    imagemanip_libraries = ['m']
else:
    imagemanip_libraries = []

pythoninc = sysconfig.get_python_inc()
numpyinc = numpy.get_include()
numpynumarrayinc = nn.get_numarray_include_dirs()

IMAGEMANIP_EXTENSIONS = [Extension('imagemanip.bilinearinterp',['imagemanip/src/bilinearinterp.c'],
                             include_dirs = [pythoninc,numpyinc],
                             libraries = imagemanip_libraries)]
                        
