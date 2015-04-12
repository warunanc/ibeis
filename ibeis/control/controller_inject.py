from __future__ import absolute_import, division, print_function
import utool as ut
#import sys
import flask
from flask import current_app, request
from functools import wraps
from os.path import abspath, join
import simplejson as json
import traceback
print, print_, printDBG, rrr, profile = ut.inject(__name__, '[controller_inject]')


#INJECTED_MODULES = []

GLOBAL_APP_ENABLED = True
GLOBAL_APP_TEMPALTE_PATH = abspath(join('ibeis', 'web', 'templates'))
GLOBAL_APP_STATIC_PATH = abspath(join('ibeis', 'web', 'static'))
GLOBAL_APP = flask.Flask('IBEIS', template_folder=GLOBAL_APP_TEMPALTE_PATH, static_folder=GLOBAL_APP_STATIC_PATH)


class WebException(Exception):
    def __init__(self, message, code=400):
        self.code = code
        self.message = message

    def __str__(self):
        return repr('%r: %r' % (self.code, self.message, ))


def translate_ibeis_webreturn(rawreturn, success=True, code=None, message=None):
    import simplejson as json
    if code is None:
        code = ''
    if message is None:
        message = ''
    template = {
        'status': {
            'success': success,
            'code':    code,
            'message': message,
        },
        'response' : rawreturn
    }
    return json.dumps(template)


def translate_ibeis_webcall(func, *args, **kwargs):
    def _process_input(multidict):
        for (arg, value) in multidict.iterlists():
            if len(value) > 1:
                raise WebException('Cannot specify a parameter more than once: %r' % (arg, ))
            value = str(value[0])
            if ',' in value:
                value = '[%s]' % (value, )
            print('VALUE: %r' % (value, ))
            kwargs[arg] = json.loads(value)
    # Pipe web input into Python web call
    _process_input(request.args)
    _process_input(request.form)
    ibs = current_app.ibs
    try:
        output = func(*args, **kwargs)
    except TypeError:
        output = func(ibs=ibs, *args, **kwargs)
    return (output, True, None, None)


def get_ibeis_flask_api():
    if GLOBAL_APP_ENABLED:
        def register_api(rule, **options):
            # accpet args to flask.route
            def regsiter_closure(func):
                # make translation function in closure scope
                # and register it with flask.
                @GLOBAL_APP.route(rule, **options)
                @wraps(func)
                def translated_call(*args, **kwargs):
                    from flask import make_response
                    try:
                        rawreturn, success, code, message = translate_ibeis_webcall(func, *args, **kwargs)
                    except WebException as webex:
                        rawreturn = str(traceback.format_exc())
                        success = False
                        code = webex.code
                        message = webex.message
                    except Exception as ex:
                        rawreturn = str(traceback.format_exc())
                        success = False
                        code = 400
                        message = 'API error, Python Exception thrown: %r' % (str(ex))
                    webreturn = translate_ibeis_webreturn(rawreturn, success, code, message)
                    return make_response(webreturn)
                # return the original unmodified function
                return func
            return regsiter_closure
        return register_api
    else:
        return ut.dummy_args_decor


def get_ibeis_flask_route():
    if GLOBAL_APP_ENABLED:
        def register_route(rule, **options):
            # accpet args to flask.route
            def regsiter_closure(func):
                # make translation function in closure scope
                # and register it with flask.
                @GLOBAL_APP.route(rule, **options)
                @wraps(func)
                def translated_call(*args, **kwargs):
                    try:
                        result = func(*args, **kwargs)
                    except Exception as ex:
                        rawreturn = str(traceback.format_exc())
                        success = False
                        code = 400
                        message = 'Route error, Python Exception thrown: %r' % (str(ex), )
                        result = translate_ibeis_webreturn(rawreturn, success, code, message)
                    return result
                # return the original unmodified function
                return func
            return regsiter_closure
        return register_route
    else:
        return ut.dummy_args_decor


def make_ibs_register_decorator(modname):
    """
    builds variables and functions that controller injectable modules need
    """
    #global INJECTED_MODULES
    if __name__ == '__main__':
        print('WARNING: cannot register controller functions as main')
    #else:
    CLASS_INJECT_KEY = ('IBEISController', modname)
    # Create dectorator to inject these functions into the IBEISController
    #register_ibs_aliased_method   = ut.make_class_method_decorator(CLASS_INJECT_KEY)
    register_ibs_unaliased_method = ut.make_class_method_decorator(CLASS_INJECT_KEY, modname)

    # TODO Replace IBEISContoller INEJECTED MODULES with this one
    #INJECTED_MODULES.append(sys.modules[modname])

    def register_ibs_method(func):
        """ registers autogenerated functions with the utool class method injector """
        #func  = profile(func)
        register_ibs_unaliased_method(func)
        #aliastup = (func, '_injected_' + ut.get_funcname(func))
        #register_ibs_aliased_method(aliastup)
        return func
    return CLASS_INJECT_KEY, register_ibs_method


r"""
Vim add decorator
%s/^\n^@\([^r]\)/\r\r@register_ibs_method\r@\1/gc
%s/^\n\(def .*(ibs\)/\r\r@register_ibs_method\r\1/gc
%s/\n\n\n\n/\r\r\r/gc

# FIND UNREGISTERED METHODS
/^[^@]*\ndef
"""


def sort_module_functions():
    from os.path import dirname, join
    import utool as ut
    import ibeis.control
    import re
    #import re
    #regex = r'[^@]*\ndef'
    modfpath = dirname(ibeis.control.__file__)
    fpath = join(modfpath, 'manual_annot_funcs.py')
    #fpath = join(modfpath, 'manual_dependant_funcs.py')
    #fpath = join(modfpath, 'manual_lblannot_funcs.py')
    #fpath = join(modfpath, 'manual_name_species_funcs.py')
    text = ut.read_from(fpath, verbose=False)
    lines =  text.splitlines()
    indent_list = [ut.get_indentation(line) for line in lines]
    isfunc_list = [line.startswith('def ') for line in lines]
    isblank_list = [len(line.strip(' ')) == 0 for line in lines]
    isdec_list = [line.startswith('@') for line in lines]

    tmp = ['def' if isfunc else indent for isfunc, indent in  zip(isfunc_list, indent_list)]
    tmp = ['b' if isblank else t for isblank, t in  zip(isblank_list, tmp)]
    tmp = ['@' if isdec else t for isdec, t in  zip(isdec_list, tmp)]
    #print('\n'.join([str((t, count + 1)) for (count, t) in enumerate(tmp)]))
    block_list = re.split('\n\n\n', text, flags=re.MULTILINE)

    #for block in block_list:
    #    print('#====')
    #    print(block)

    isfunc_list = [re.search('^def ', block, re.MULTILINE) is not None for block in block_list]

    whole_varname = ut.whole_word(ut.REGEX_VARNAME)
    funcname_regex = r'def\s+' + ut.named_field('funcname', whole_varname)

    def findfuncname(block):
        match = re.search(funcname_regex, block)
        return match.group('funcname')

    funcnameblock_list = [findfuncname(block) if isfunc else None for isfunc, block in zip(isfunc_list, block_list)]

    funcblock_list = ut.filter_items(block_list, isfunc_list)
    funcname_list = ut.filter_items(funcnameblock_list, isfunc_list)

    nonfunc_list = ut.filterfalse_items(block_list, isfunc_list)

    nonfunc_list = ut.filterfalse_items(block_list, isfunc_list)
    ismain_list = [re.search('^if __name__ == ["\']__main__["\']', nonfunc) is not None for nonfunc in nonfunc_list]

    mainblock_list = ut.filter_items(nonfunc_list, ismain_list)
    nonfunc_list = ut.filterfalse_items(nonfunc_list, ismain_list)

    newtext_list = []

    for nonfunc in nonfunc_list:
        newtext_list.append(nonfunc)
        newtext_list.append('\n')

    #funcname_list
    for funcblock in ut.sortedby(funcblock_list, funcname_list):
        newtext_list.append(funcblock)
        newtext_list.append('\n')

    for mainblock in mainblock_list:
        newtext_list.append(mainblock)

    newtext = '\n'.join(newtext_list)
    print(newtext)
    print(len(newtext))
    print(len(text))

    backup_fpath = ut.augpath(fpath, augext='.bak', augdir='_backup', ensure=True)

    ut.write_to(backup_fpath, text)
    ut.write_to(fpath, newtext)

    #for block, isfunc in zip(block_list, isfunc_list):
    #    if isfunc:
    #        print(block)

    #for block, isfunc in zip(block_list, isfunc_list):
    #    if isfunc:
    #        print('----')
    #        print(block)
    #        print('\n')


def find_unregistered_methods():
    r"""
    CommandLine:
        python -m ibeis.control.controller_inject --test-find_unregistered_methods --enableall

    Example:
        >>> # ENABLE_DOCTEST
        >>> from ibeis.control.controller_inject import *  # NOQA
        >>> result = find_unregistered_methods()
        >>> print(result)
    """
    from os.path import dirname
    import utool as ut
    import ibeis.control
    import re
    #regex = r'[^@]*\ndef'
    modfpath = dirname(ibeis.control.__file__)
    fpath_list = ut.glob(modfpath, 'manual_*_funcs.py')
    #fpath_list += ut.glob(modfpath, '_autogen_*_funcs.py')

    def multiline_grepfile(regex, fpath):
        found_matchtexts = []
        found_linenos   = []
        text = ut.read_from(fpath, verbose=False)
        for match in  re.finditer(regex, text, flags=re.MULTILINE):
            lineno = text[:match.start()].count('\n')
            matchtext = ut.get_match_text(match)
            found_linenos.append(lineno)
            found_matchtexts.append(matchtext)
        return found_matchtexts, found_linenos

    def multiline_grep(regex, fpath_list):
        found_fpath_list      = []
        found_matchtexts_list = []
        found_linenos_list    = []
        for fpath in fpath_list:
            found_matchtexts, found_linenos = multiline_grepfile(regex, fpath)
            # append anything found in this file
            if len(found_matchtexts) > 0:
                found_fpath_list.append(fpath)
                found_matchtexts_list.append(found_matchtexts)
                found_linenos_list.append(found_linenos)
        return found_fpath_list, found_matchtexts_list, found_linenos_list

    def print_mutliline_matches(tup):
        found_fpath_list, found_matchtexts_list, found_linenos_list = tup
        for fpath, found_matchtexts, found_linenos in zip(found_fpath_list, found_matchtexts_list, found_linenos_list):
            print('+======')
            print(fpath)
            for matchtext, lineno in zip(found_matchtexts, found_linenos):
                print('    ' + '+----')
                print('    ' + str(lineno))
                print('    ' + str(matchtext))
                print('    ' + 'L____')

    #print(match)
    print('\n\n GREPING FOR UNDECORATED FUNCTIONS')
    regex = '^[^@\n]*\ndef\\s.*$'
    tup = multiline_grep(regex, fpath_list)
    print_mutliline_matches(tup)

    print('\n\n GREPING FOR UNDECORATED FUNCTION ALIASES')
    regex = '^' + ut.REGEX_VARNAME + ' = ' + ut.REGEX_VARNAME
    tup = multiline_grep(regex, fpath_list)
    print_mutliline_matches(tup)
    #ut.grep('aaa\rdef', modfpath, include_patterns=['manual_*_funcs.py', '_autogen_*_funcs.py'], reflags=re.MULTILINE)


if __name__ == '__main__':
    """
    CommandLine:
        python -m ibeis.control.controller_inject
        python -m ibeis.control.controller_inject --allexamples
        python -m ibeis.control.controller_inject --allexamples --noface --nosrc
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
