import time
from pyscreeze import PyScreezeException, center, locateAll, pixel, pixelMatchesColor, screenshot

USE_IMAGE_NOT_FOUND_EXCEPTION = True

class ImageNotFoundException(PyScreezeException):
    """ImageNotFoundException is an exception class raised when the
    locate functions fail to locate an image. You must set
    pyscreeze.USE_IMAGE_NOT_FOUND_EXCEPTION to True to enable this feature.
    Otherwise, the locate functions will return None."""
    pass

def locate(needleImage, haystackImage, **kwargs):
    # Note: The gymnastics in this function is because we want to make sure to exhaust the iterator so that
    # the needle and haystack files are closed in locateAll.
    kwargs['limit'] = 1
    points = tuple(locateAll(needleImage, haystackImage, **kwargs))
    if len(points) > 0:
        return points[0]
    else:
        if USE_IMAGE_NOT_FOUND_EXCEPTION:
            raise ImageNotFoundException('Could not locate the image.')
        else:
            return None

def locateOnScreen(image, minSearchTime=0, **kwargs):
    start = time.time()
    while True:
        try:
            # the locateAll() function must handle cropping to return accurate coordinates,
            # so don't pass a region here.
            screenshotIm = screenshot(region=kwargs.get('region', None))
            kwargs_without_region = {k: v for k, v in kwargs.items() if k != 'region'}
            retVal = locate(image, screenshotIm, **kwargs_without_region)
            if retVal and 'region' in kwargs:
                region = kwargs['region']
                retVal = retVal._replace(
                    left=retVal.left + region[0],
                    top=retVal.top + region[1]
                )
            try:
                screenshotIm.fp.close()
            except AttributeError:
                # Screenshots on Windows won't have an fp since they came from
                # ImageGrab, not a file. Screenshots on Linux will have fp set
                # to None since the file has been unlinked
                pass
            if retVal or time.time() - start > minSearchTime:
                return retVal
        except ImageNotFoundException:
            if time.time() - start > minSearchTime:
                if USE_IMAGE_NOT_FOUND_EXCEPTION:
                    raise
                else:
                    return None