from __future__ import print_function, division
import sys
from functools import wraps
from itertools import islice, imap
from .util_iter import isiterable
from .util_print import Indenter, printVERBOSE
import numpy as np
import pylru  # because we dont have functools.lru_cache
from .util_inject import inject
(print, print_, printDBG, rrr, profile) = inject(__name__, '[decor]')

IGNORE_EXC_TB = not '--noignore-exctb' in sys.argv


def ignores_exc_tb(func):
    """ decorator that removes other decorators from traceback """
    if IGNORE_EXC_TB:
        @wraps(func)
        def wrapper_ignore_exctb(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                # Code to remove this decorator from traceback
                exc_type, exc_value, exc_traceback = sys.exc_info()
                # Remove two levels to remove this one as well
                raise exc_type, exc_value, exc_traceback.tb_next.tb_next
        return wrapper_ignore_exctb
    else:
        return func


def indent_decor(lbl):
    def indent_decor_outer_wrapper(func):
        @ignores_exc_tb
        @wraps(func)
        def indent_decor_inner_wrapper(*args, **kwargs):
            with Indenter(lbl):
                return func(*args, **kwargs)
        return indent_decor_inner_wrapper
    return indent_decor_outer_wrapper


def indent_func(func):
    @wraps(func)
    @indent_decor('[' + func.func_name + ']')
    @ignores_exc_tb
    def wrapper_indent_func(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper_indent_func


def accepts_scalar_input(func):
    '''
    accepts_scalar_input is a decorator which expects to be used on class methods.
    It lets the user pass either a vector or a scalar to a function, as long as
    the function treats everything like a vector. Input and output is sanatized
    to the user expected format on return.
    '''
    @ignores_exc_tb
    @wraps(func)
    def wrapper_scalar_input(self, input_, *args, **kwargs):
        is_scalar = not isiterable(input_)
        if is_scalar:
            iter_input = (input_,)
        else:
            iter_input = input_
        result = func(self, iter_input, *args, **kwargs)
        if is_scalar:
            result = result[0]
        return result
    return wrapper_scalar_input


def accepts_scalar_input_vector_output(func):
    '''
    accepts_scalar_input is a decorator which expects to be used on class
    methods.  It lets the user pass either a vector or a scalar to a function,
    as long as the function treats everything like a vector. Input and output is
    sanatized to the user expected format on return.
    '''
    @ignores_exc_tb
    @wraps(func)
    def wrapper_vec_output(self, input_, *args, **kwargs):
        is_scalar = not isiterable(input_)
        if is_scalar:
            iter_input = (input_,)
        else:
            iter_input = input_
        result = func(self, iter_input, *args, **kwargs)
        if is_scalar:
            if len(result) != 0:
                result = result[0]
        return result
    return wrapper_vec_output


def accepts_numpy(func):
    """ Allows the first input to be a numpy objet and get result in numpy form """
    @wraps(func)
    def numpy_wrapper(self, input_, *args, **kwargs):
        if isinstance(input_, np.ndarray):
            input_list = input_.flatten()
            output_list = func(self, input_list)
            output_ = np.array(output_list).reshape(input_.shape)
        else:
            output_ = func(self, input_)
        return output_
    return numpy_wrapper


class lru_cache(object):
    """
        Python 2.7 does not have functools.lrucache. Here is an alternative
        implementation. This can currently only wrap class functions
    """
    def __init__(cache, max_size=100, nInput=1):
        cache.max_size = max_size
        cache.nInput = nInput
        cache.cache_ = pylru.lrucache(max_size)
        cache.func_name = None

    def clear_cache(cache):
        printDBG('[cache.lru] clearing %r lru_cache' % (cache.func_name,))
        cache.cache_.clear()

    def __call__(cache, func):
        def wrapped(self, *args, **kwargs):  # wrap a class
            key = tuple(imap(tuple, islice(args, 0, cache.nInput)))
            try:
                value = cache.cache_[key]
                printVERBOSE(func.func_name + ' ...lrucache HIT', '--verbose-lru')
                return value
            except KeyError:
                printVERBOSE(func.func_name + ' ...lrucache MISS', '--verbose-lru')

            value = func(self, *args, **kwargs)
            cache.cache_[key] = value
            return value
        cache.func_name = func.func_name
        printDBG('[@decor.lru] wrapping %r with max_size=%r lru_cache' %
                 (cache.func_name, cache.max_size))
        wrapped.func_name = func.func_name
        wrapped.clear_cache = cache.clear_cache
        return wrapped
