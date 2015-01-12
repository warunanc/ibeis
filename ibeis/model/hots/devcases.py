"""
development module storing my "development state"

TODO:
    * figure out what packages I use have lisencing issues.
        - Reimplement them or work around them.
"""
from __future__ import absolute_import, division, print_function
from ibeis.model.hots import hstypes
from uuid import UUID
import utool as ut
import six
import copy
import numpy as np  # NOQA
print, print_, printDBG, rrr, profile = ut.inject(__name__, '[devcases]')


def myquery():
    r"""

    see how seperability changes as we very things
    pas

    CommandLine:
        python -m ibeis.model.hots.devcases --test-myquery
        python -m ibeis.model.hots.devcases --test-myquery

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.all_imports import *  # NOQA
        >>> from ibeis.model.hots.devcases import *  # NOQA
        >>> if ut.inIPython():
        >>>     ut.dev_ipython_copypaster(myquery)
        >>> elif not ut.inIPython():
        >>>     myquery()
    """
    import ibeis
    import utool as ut
    from ibeis.model.hots import special_query  # NOQA
    from ibeis import viz  # NOQA
    from uuid import UUID
    ibs = ibeis.opendb('GZ_ALL')
    vsone_pair_examples = [
        [UUID('8415b50f-2c98-0d52-77d6-04002ff4d6f8'), UUID('308fc664-7990-91ad-0576-d2e8ea3103d0')],
        [UUID('490f76bf-7616-54d5-576a-8fbc907e46ae'), UUID('2046509f-0a9f-1470-2b47-5ea59f803d4b')],
        [UUID('5cdf68ab-be49-ee3f-94d8-5483772c8618'), UUID('879977a7-b841-d223-dd91-761dfa58d486')],
    ]
    gf_mapping = {
        UUID('5cdf68ab-be49-ee3f-94d8-5483772c8618'): [UUID('5a8c8ad7-873a-e6ed-98df-56a452e0a93e')],
    }

    #ibs.get_annot_visual_uuids([36, 3])

    vuuid_pair = vsone_pair_examples[2]
    vuuid1, vuuid2 = vuuid_pair
    aid1, aid2 = ibs.get_annot_aids_from_visual_uuid(vuuid_pair)
    #daids = ibs.get_valid_aids()

    use_cache = False
    save_qcache = False

    bad_vuuid = gf_mapping.get(vuuid1)
    bad_aids = ibs.get_annot_aids_from_visual_uuid(bad_vuuid)
    bad_aid = bad_aids[0]
    qaids = [aid1]
    daids = [aid2] + bad_aids

    """
    viz.show_chip(ibs, aid1)
    import plottool as pt
    pt.update()
    """

    cfgdict_vsone = dict(
        sv_on=True,
        #sv_on=False,
        codename='vsone_unnorm_extern_distinctiveness'
    )

    qres_list, qreq_ = ibs.query_chips(qaids, daids, cfgdict=cfgdict_vsone,
                                       return_request=True, use_cache=use_cache,
                                       save_qcache=save_qcache, verbose=True)
    qres = qres_list[0]
    top_aids = qres.get_top_aids()  # NOQA
    qres_orig = qres  # NOQA
    #[.5, 1.0, 1.5]
    diff_list = []
    good_score_list = []
    bad_score_list = []
    #p=np.linspace(.1, 2.0, 5)
    grid_basis = [
        ut.util_dict.DimensionBasis('p', [.5, 1.0]),
        ut.util_dict.DimensionBasis('K', [2, 3, 4, 5]),
    ]
    cfgdict_iter = ut.grid_search_generator(grid_basis)
    cfgdict_list = list(cfgdict_iter)
    for cfgdict in cfgdict_list:
        qres_copy = copy.deepcopy(qres_orig)
        qreq_vsone_ = qreq_
        qres_vsone = qres_copy
        filtkey = hstypes.FiltKeys.DISTINCTIVENESS
        newfsv_list, newscore_aids = special_query.get_extern_distinctiveness(qreq_, qres_copy, **cfgdict)
        special_query.apply_new_qres_filter_scores(qreq_vsone_, qres_vsone, newfsv_list, newscore_aids, filtkey)
        good_score = qres_copy.aid2_score[aid2]
        bad_score = qres_copy.aid2_score[bad_aid]
        diff = good_score - bad_score
        diff_list.append(diff)
        #qres_copy.ishow_top(ibs, annot_mode=1)
        good_score_list.append(good_score)
        bad_score_list.append(bad_score)
    # Input Parameters
    param_name_list = ut.get_list_column(grid_basis, 0)
    params_vals = [list(six.itervalues(dict_)) for dict_ in cfgdict_list]
    param_vals_list = list(zip(*params_vals))
    # Result Scores
    score_list  = [diff_list, good_score_list, bad_score_list]
    score_lbls  = ['score_diff', 'good_score', 'bad_score']

    score_lbl  = 'score_diff'
    sort_vals = score_list[score_lbls.index(score_lbl)]
    sortby_func = ut.make_sortby_func(sort_vals, reverse=True)

    score_name_sorted = score_lbls
    param_name_sorted = param_name_list
    score_list_sorted = list(map(sortby_func, score_list))
    param_vals_sorted = list(map(sortby_func, param_vals_list))

    # Build CSV
    column_lbls = score_name_sorted + param_name_sorted
    column_list = score_list_sorted + param_vals_sorted
    header_raw = ut.codeblock('''
    import utool as ut
    DimensionBasis = ut.util_dict.DimensionBasis
    title = 'Grid Search Results CSV'
    grid_basis = ''') + ut.list_str(grid_basis)
    header = ut.indent(header_raw, '# >>> ')
    ut.rrrr()
    precision = 3
    csvtext = ut.make_csv_table(column_list, column_lbls, header, precision=precision)
    print(csvtext)
    #print(ut.list_str()))

    # TODO: plot max variation dims
    #import plottool as pt
    #pt.plot(p_list, diff_list)

    # PRINT INFO
    #print('qres_copy.filtkey_list = %r' % (qres_copy.filtkey_list,))
    #print('CORRECT STATS')
    #print(ut.get_stats_str(qres_copy.aid2_fsv[aid2], axis=0, newlines=True))
    #print('INCORRECT STATS')
    #print(ut.get_stats_str(qres_copy.aid2_fsv[bad_aid], axis=0, newlines=True))


def find_close_incorrect_match(ibs, qaids):
    use_cache = False
    save_qcache = False
    cfgdict_vsmany = dict(index_method='single',
                          pipeline_root='vsmany',)
    qres_vsmany_list, qreq_vsmany_ = ibs.query_chips(
        qaids, ibs.get_valid_aids(), cfgdict=cfgdict_vsmany,
        return_request=True, use_cache=use_cache, save_qcache=save_qcache,
        verbose=True)
    qres_vsmany = qres_vsmany_list[0]
    qres_vsmany.ishow_top(ibs)
    top_aids = qres_vsmany.get_top_aids()
    top_nids = ibs.get_annot_nids(top_aids)
    qaid = qaids[0]
    qnid = ibs.get_annot_nids(qaid)
    is_groundfalse = [nid != qnid for nid in top_nids]
    top_gf_aids = ut.filter_items(top_aids, is_groundfalse)
    #top_gt_aids = ut.filterfalse_items(top_aids, is_groundfalse)
    top_gf_vuuids = ibs.get_annot_visual_uuids(top_gf_aids)
    qvuuid = ibs.get_annot_visual_uuids(qaid)
    gf_mapping = {qvuuid: top_gf_vuuids[0:1]}
    print('gf_mapping = ' + ut.dict_str(gf_mapping))
    pass


def get_gzall_small_test():
    """
    ibs.get_annot_visual_uuids([qaid, aid])
    """
    #aid_list = [839, 999, 1047, 209, 307, 620, 454, 453, 70, 1015, 939, 1021,
    #              306, 742, 1010, 802, 619, 1041, 27, 420, 740, 1016, 140, 992,
    #              1043, 662, 816, 793, 994, 867, 534, 986, 783, 858, 937, 60,
    #              879, 1044, 528, 459, 639]
    debug_examples = [
        UUID('308fc664-7990-91ad-0576-d2e8ea3103d0'),
    ]
    #vsone_pair_examples
    debug_examples

    ignore_vuuids = [
        UUID('be6fe4d6-ae87-0f8f-269f-e9f706b69e41'),  # OUT OF PLANE
        UUID('c3394b28-e7f2-2da6-1a49-335b748acf9e'),  # HUGE OUT OF PLANE, foal (vsmany gets rank3)
        UUID('490f76bf-7616-54d5-576a-8fbc907e46ae'),
        UUID('2046509f-0a9f-1470-2b47-5ea59f803d4b'),
    ]
    vuuid_list = [
        UUID('e9a9544d-083d-6c30-b00f-d6806824a21a'),
        UUID('153306d8-e9f8-b5a6-a06d-90ddb7de6c17'),
        UUID('04908b6f-b775-46f1-e9ec-fd834d9fe046'),
        UUID('20817244-12d1-bcf4-dac8-b787c064e6b4'),
        UUID('7ad8b4fc-f057-bac9-0b1a-fa05db09b685'),
        UUID('df418005-ce26-e439-ab43-00f56447a3c8'),
        UUID('2ca8c5b0-ae45-a1a2-11fb-3497dfd58736'),
        UUID('7c6fd123-ad9c-7360-8b7c-b8d694ac4057'),
        UUID('98e87153-4437-562b-9f77-d7c58495cfea'),
        UUID('7bb9b77a-7ad5-44f3-4352-bf6bf901323a'),
        UUID('863786d9-853d-859d-f726-13796fc0a257'),
        UUID('9c1b04bc-7af1-bd3f-85d3-7c06c8b0d0a7'),
        UUID('c0775a6d-f3a9-f1d2-1a92-cfc4817ecedf'),
        UUID('52668d79-8065-bae4-29ca-0f393e8b0331'),
        UUID('86bf60e5-20a8-0e8d-590c-836ac4723d23'),
        UUID('2046509f-0a9f-1470-2b47-5ea59f803d4b'),
        UUID('a0444615-1264-8768-8a4e-fbc2cafb76ce'),
        UUID('308fc664-7990-91ad-0576-d2e8ea3103d0'),  # testcase
        UUID('4bd156a3-0315-72fd-d181-309b92f21d58'),
        UUID('04815be5-fee7-f34d-e2cd-6130914e2071'),
        UUID('815a8276-8812-35a3-d1e5-963c2047edc5'),
        UUID('2d94da8d-0d97-815d-d350-bf3ab1caaf23'),
        UUID('9732e459-4c73-c8d5-3911-59c6e66d81f8'),
        UUID('38e39dda-bae3-ce19-f7d3-a50fc1c3554d'),
        UUID('1509cad7-e368-6d95-9047-552d054ddabd'),
        UUID('2091fa5b-bf9d-25ba-b539-9156202dd522'),
        UUID('fc94609f-b378-9877-d0ac-433993e7f6bd'),
        UUID('914f1c91-c22b-a4b5-77f8-59423bc6d99d'),
        UUID('249f7615-95e2-ea66-649f-ec8021e5aa41'),
        UUID('2de71fb1-dd7c-a7de-2e0d-0be399286d09'),
        UUID('94010938-cb14-c209-5488-5372b81d1eb1'),
        UUID('d75a9205-efc4-a078-a533-bdde5345b74a'),
        UUID('99a1e02a-0e3d-cd9a-b410-902f5d8cf308'),
        UUID('193ade79-eff2-f888-7f15-27a399c505b0'),
        UUID('190bf50d-9729-48c3-47b6-acefc6f3ef03'),
        UUID('5345c6dc-bc52-43ec-d792-0e7c9e7ec3b5'),
        UUID('10757fe8-8fd3-ad59-f550-c941da967b82'),
        UUID('89859efb-a233-5e43-fb5e-c36e9d446a1e'),
        UUID('265cf095-64f6-e5dd-8f7d-2a82f627b7d1'),
        UUID('4b19968e-f813-f238-0dcc-6a54f1943d57')]
    return vuuid_list, ignore_vuuids


def load_gztest(ibs):
    r"""
    CommandLine:
        python -m ibeis.model.hots.special_query --test-load_gztest

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.model.hots.devcases import *  # NOQA
        >>> import ibeis
        >>> ibs = ibeis.opendb('GZ_ALL')
    """
    from os.path import join
    from ibeis.model.hots import match_chips4 as mc4
    dir_ = ut.get_module_dir(mc4)
    eval_text = ut.read_from(join(dir_,  'GZ_TESTTUP.txt'))
    testcases = eval(eval_text)
    count_dict = ut.count_dict_vals(testcases)
    print(ut.dict_str(count_dict))

    testtup_list = ut.flatten(ut.dict_take_list(testcases, ['vsone_wins',
                                                            'vsmany_outperformed',
                                                            'vsmany_dominates',
                                                            'vsmany_wins']))
    qaid_list = [testtup.qaid_t for testtup in testtup_list]
    visual_uuids = ibs.get_annot_visual_uuids(qaid_list)
    visual_uuids


if __name__ == '__main__':
    """
    CommandLine:
        python -m ibeis.model.hots.devcases
        python -m ibeis.model.hots.devcases --allexamples
        python -m ibeis.model.hots.devcases --allexamples --noface --nosrc
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
