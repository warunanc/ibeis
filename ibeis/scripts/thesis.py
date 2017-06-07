# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals  # NOQA
from ibeis.scripts import script_vsone
import ibeis.constants as const
from ibeis.algo.graph import nx_utils as nxu
import ubelt as ub
import pandas as pd
import numpy as np
from os.path import basename, join, splitext, exists
import utool as ut
import plottool as pt
import vtool as vt
import pathlib
import matplotlib as mpl
import random
import six
import sys
from ibeis.algo.graph.state import POSTV, NEGTV, INCMP  # NOQA
(print, rrr, profile) = ut.inject2(__name__)

DPI = 300

TMP_RC = {
    'axes.titlesize': 12,
    'axes.labelsize': 12,
    'font.family': 'DejaVu Sans',
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    # 'legend.fontsize': 18,
    # 'legend.alpha': .8,
    'legend.fontsize': 12,
    'legend.facecolor': 'w',
}

TMP_RC = {
    'axes.titlesize': 12,
    'axes.labelsize': ut.get_argval('--labelsize', default=12),
    'font.family': 'sans-serif',
    'font.serif': 'CMU Serif',
    'font.sans-serif': 'CMU Sans Serif',
    'font.monospace': 'CMU Typewriter Text',
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    # 'legend.alpha': .8,
    'legend.fontsize': 12,
    'legend.facecolor': 'w',
}

W, H = 7.4375, 3.0


class DBInputs(object):

    def __init__(self, dbname=None):
        self.dbname = dbname
        if 'GZ' in dbname:
            self.species_nice = "Grévy's zebras"
        if 'PZ' in dbname:
            self.species_nice = "plains zebras"
        if 'GIRM' in dbname:
            self.species_nice = "Masai giraffes"
        if 'humpback' in dbname:
            self.species_nice = "Humpbacks"
        self.ibs = None
        if dbname is not None:
            self.dpath = join(self.base_dpath, self.dbname)
            # ut.ensuredir(self.dpath)
        self.expt_results = {}

    @classmethod
    def measure(ChapX, expt_name, dbnames, *args):
        """
        CommandLine:
            python -m ibeis Chap3.measure all --dbs=GZ_Master1
            python -m ibeis Chap3.measure all --dbs=PZ_Master1

            python -m ibeis Chap3.measure nsum --dbs=GZ_Master1,PZ_Master1
            python -m ibeis Chap3.measure foregroundness --dbs=GZ_Master1,PZ_Master1

        # Example:
        #     >>> # Script
        #     >>> from ibeis.scripts.thesis import *  # NOQA
        #     >>> expt_name = ut.get_argval('--expt', type_=str, pos=1)
        #     >>> dbnames = ut.get_argval(('--dbs', '--db'), type_=list, default=[])
        #     >>> ChapX.measure(expt_name, dbnames)
        """
        print('expt_name = %r' % (expt_name,))
        print('dbnames = %r' % (dbnames,))
        print('args = %r' % (args,))
        dbnames = ut.smart_cast(dbnames, list)
        for dbname in dbnames:
            self = ChapX(dbname)
            if self.ibs is None:
                self._setup()
                # self._precollect()
            if expt_name == 'all':
                self.measure_all(*args)
            else:
                getattr(self, 'measure_' + expt_name)(*args)

    @classmethod
    def draw(ChapX, expt_name, dbnames, *args):
        """
        CommandLine:
            python -m ibeis Chap3.draw nsum --dbs=GZ_Master1,PZ_Master1
            python -m ibeis Chap3.draw foregroundness --dbs=GZ_Master1,PZ_Master1 --diskshow
            python -m ibeis Chap3.draw kexpt --dbs=GZ_Master1 --diskshow

            python -m ibeis Chap4.draw importance GZ_Master1

            python -m ibeis Chap4.draw hard_cases GZ_Master1,PZ_Master1 match_state,photobomb_state
            --diskshow

        # Example:
        #     >>> # Script
        #     >>> from ibeis.scripts.thesis import *  # NOQA
        #     >>> expt_name = ut.get_argval('--expt', type_=str, pos=1)
        #     >>> dbnames = ut.get_argval(('--dbs', '--db'), type_=list, default=[])
        #     >>> Chap3.draw(expt_name, dbnames)
        """
        print('expt_name = %r' % (expt_name,))
        print('dbnames = %r' % (dbnames,))
        print('args = %r' % (args,))
        dbnames = ut.smart_cast(dbnames, list)

        if len(dbnames) > 1:
            from concurrent import futures
            multi_args = [ut.smart_cast(a, list) for a in args]
            with futures.ProcessPoolExecutor(max_workers=6) as executor:
                list(futures.as_completed([
                    executor.submit(ChapX.draw, expt_name, *fsargs)
                    for fsargs in ut.product(dbnames, *multi_args)
                ]))
            print('\n\n Completed multiple tasks')
        else:
            for dbname in dbnames:
                self = ChapX(dbname)
                if expt_name == 'all':
                    self.draw_all()
                else:
                    draw_func = getattr(self, 'draw_' + expt_name, None)
                    if draw_func is None:
                        draw_func = getattr(self, 'write_' + expt_name, None)
                    if draw_func is None:
                        raise ValueError('Cannot find a way to draw ' + expt_name)
                    fpath = draw_func(*args)
                    if ut.get_argflag('--diskshow'):
                        if isinstance(fpath, six.text_type):
                            ut.startfile(fpath)
                        else:
                            fpath_list = fpath
                            for fpath in fpath_list:
                                ut.startfile(fpath)

    @profile
    def _precollect(self):
        """
        Sets up an ibs object with an aids_pool

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> self = Chap3('humpbacks_fb')
            >>> self = Chap3('GZ_Master1')
            >>> self = Chap3('GIRM_Master1')
            >>> self = Chap3('PZ_MTEST')
            >>> self = Chap3('PZ_PB_RF_TRAIN')
            >>> self = Chap3('PZ_Master1')
            >>> self._precollect()

            >>> from ibeis.scripts.thesis import *
            >>> self = Chap4('PZ_Master1')
            >>> self._precollect()
        """
        import ibeis
        from ibeis.init import main_helpers
        self.dbdir = ibeis.sysres.lookup_dbdir(self.dbname)
        ibs = ibeis.opendb(dbdir=self.dbdir)
        if ibs.dbname.startswith('PZ_PB_RF_TRAIN'):
            aids = ibs.get_valid_aids()
        elif ibs.dbname.startswith('PZ_Master'):
            if False:
                # OLD WAY OF RUNNING THAT WAS USED TO GENERATE CHAPTER 3
                # EXPERIMENTS.
                aids = ibs.filter_annots_general(
                    # FIXME view_ext does not work
                    require_timestamp=True, is_known=True, species='primary',
                    min_pername=2, minqual='poor')
                # We need to do our best to select a small sample here
                flags = ['left' in text for text in ibs.annots(aids).yaw_texts]
                aids = ut.compress(aids, flags)
                # This produces 6474 annotations
                # print(len(aids))
            else:
                # NEW WAY OF RUNNING FOR CHAPTERS 4 and 5.  WE REALLY SHOULD DO
                # ALL CHAPTERS WITH THE SAME.  IF POSSIBLE.

                # PZ_Master is too big to run in full.  Select a smaller sample.
                # Be sure to include photobomb and incomparable cases.
                aids = ibs.filter_annots_general(
                    require_timestamp=True, species='primary', is_known=True,
                    minqual='poor',
                )
                infr = ibeis.AnnotInference(ibs=ibs, aids=aids)
                infr.reset_feedback('staging', apply=True)
                minority_ccs = find_minority_class_ccs(infr)
                minority_aids = set(ut.flatten(minority_ccs))

                # We need to do our best to select a small sample here
                flags = ['left' in text for text in ibs.annots(aids).yaw_texts]
                left_aids = ut.compress(aids, flags)

                majority_aids = set(ibs.filter_annots_general(
                    left_aids, require_timestamp=True, species='primary',
                    minqual='poor', require_quality=True, min_pername=2,
                    max_pername=15
                ))
                # This produces 5720 annotations
                aids = sorted(majority_aids.union(minority_aids))
                # print(len(majority_aids))
                # print(len(minority_aids))
                # print(len(minority_aids.intersection(majority_aids)))
                # ibs.print_annot_stats(list(minority_aids), prefix='P')
                # ibs.print_annot_stats(list(majority_aids), prefix='P')
                # ibs.print_annot_stats(list(aids), prefix='P')

                # infr = ibeis.AnnotInference(ibs=ibs, aids=aids)
                # infr.reset_feedback('staging', apply=True)
                # print('# photobombs: %r' % infr.edge_tag_hist().get(
                #     'photobomb', 0))
                # print(ut.repr4(infr.status()))
            # flags = ['right' not in text for text in ibs.annots(aids).yaw_texts]
            # sum(['left' == text for text in ibs.annots(aids).yaw_texts])
        # elif ibs.dbname == 'GZ_Master1':
        else:
            aids = ibs.filter_annots_general(require_timestamp=True,
                                             is_known=True,
                                             species='primary',
                                             minqual='poor')
        # ibs.print_annot_stats(aids, prefix='P')
        main_helpers.monkeypatch_encounters(ibs, aids, minutes=30)
        print('post monkey patch')
        if False:
            ibs.print_annot_stats(aids, prefix='P')
        self.ibs = ibs
        self.aids_pool = aids
        if False:
            # check encounter stats
            annots = ibs.annots(aids)
            encounters = annots.group(annots.encounter_text)[1]
            nids = ut.take_column(ibs._annot_groups(encounters).nids, 0)
            nid_to_enc = ut.group_items(encounters, nids)
            nenc_list = ut.lmap(len, nid_to_enc.values())
            hist = ut.range_hist(nenc_list, [1, 2, 3, (4, np.inf)])
            print('enc per name hist:')
            print(ut.repr2(hist))

            # singletons = [a for a in encounters if len(a) == 1]
            multitons = [a for a in encounters if len(a) > 1]
            deltas = []
            for a in multitons:
                times = a.image_unixtimes_asfloat
                deltas.append(max(times) - min(times))
            ut.lmap(ut.get_posix_timedelta_str, sorted(deltas))


@ut.reloadable_class
class IOContract(object):
    """
    Subclasses must obey the measure_<expt_name>, draw_<expt_name> contract
    """

    def ensure_results(self, expt_name=None):
        if expt_name is None and exists(self.dpath):
            # Load all
            fpaths = ut.glob(str(self.dpath), '*.pkl')
            expt_names = [splitext(basename(fpath))[0] for fpath in fpaths]
            for fpath, expt_name in zip(fpaths, expt_names):
                self.expt_results[expt_name] = ut.load_data(fpath)
        else:
            fpath = join(str(self.dpath), expt_name + '.pkl')
            expt_name = splitext(basename(fpath))[0]
            if not exists(fpath):
                if self.ibs is None:
                    self._precollect()
                getattr(self, 'measure_' + expt_name)()
            self.expt_results[expt_name] = ut.load_data(fpath)
            return self.expt_results[expt_name]


@ut.reloadable_class
class Chap5(DBInputs):
    base_dpath = ut.truepath('~/latex/crall-thesis-2017/figuresGraph')

    def _setup(self):
        """
        CommandLine:
            python -m ibeis Chap5.measure simulation PZ_MTEST --show
            python -m ibeis Chap5.measure simulation GZ_Master1 --show --aug=test
            python -m ibeis Chap5.measure simulation PZ_Master1 --show --aug=test
            python -m ibeis Chap5.measure simulation GZ_Master1 --show
            python -m ibeis Chap5.measure simulation PZ_Master1 --show

            python -m ibeis Chap5.print_measures --db GZ_Master1 --diskshow
            python -m ibeis Chap5.print_measures --db PZ_Master1 --diskshow

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> self = Chap5('GZ_Master1')
            >>> self = Chap5('PZ_MTEST')
        """
        self._precollect()

        ibs = self.ibs
        annots = ibs.annots(self.aids_pool)
        names = list(annots.group_items(annots.nids).values())
        ut.shuffle(names, rng=321)
        train_aids = ut.flatten(names[0::2])
        test_aids = ut.flatten(names[1::2])

        if ibs.dbname == 'PZ_MTEST':
            params = dict(sample_method='random')
        else:
            params = dict()

        pblm = script_vsone.OneVsOneProblem.from_aids(ibs, train_aids, **params)
        task_key = 'match_state'
        data_key = pblm.default_data_key
        clf_key = pblm.default_clf_key

        pblm.eval_data_keys = [data_key]
        pblm.setup(with_simple=False)
        pblm.learn_evaluation_classifiers()

        res = pblm.task_combo_res[task_key][clf_key][data_key]
        pblm.report_evaluation()

        # if False:
        #     pblm.learn_evaluation_classifiers(task_keys=['photobomb_state'])
        #     pb_res = pblm.task_combo_res['photobomb_state'][clf_key][data_key]
        #     pb_res  # TODO?

        if True:
            # Remove results that are photobombs for now
            # res = pblm.task_combo_res['photobomb_state'][clf_key][data_key]
            pb_task = pblm.samples.subtasks['photobomb_state']
            import utool
            with utool.embed_on_exception_context:
                flags = pb_task.indicator_df.loc[res.index]['notpb'].values
                notpb_res = res.compress(flags)
                res = notpb_res

        # TODO: need more principled way of selecting thresholds
        graph_thresh = res.get_pos_threshes('fpr', value=.002)
        rankclf_thresh = res.get_pos_threshes('fpr', value=0)

        if ibs.dbname == 'GZ_Master1':
            graph_thresh = res.get_pos_threshes('fpr', value=.0014)
            rankclf_thresh = res.get_pos_threshes('fpr', value=.001)
        elif ibs.dbname == 'PZ_Master1':
            # graph_thresh = res.get_pos_threshes('fpr', value=.0014)
            # rankclf_thresh = res.get_pos_threshes('fpr', value=.001)
            graph_thresh = res.get_pos_threshes('fpr', value=.03)
            rankclf_thresh = res.get_pos_threshes('fpr', value=.01)
            # graph_thresh = res.get_pos_threshes('fpr', value=.1)
            # rankclf_thresh = res.get_pos_threshes('fpr', value=.03)

        print('\n--- Graph thresholds ---')
        res.report_auto_thresholds(graph_thresh)

        print('\n --- Ranking thresholds ---')
        res.report_auto_thresholds(rankclf_thresh)

        # Setup directory
        from os.path import expanduser
        dbcode = '{}_{}_{}'.format(ibs.dbname, len(test_aids), len(train_aids))
        dpath = expanduser(self.base_dpath + '/' + dbcode)
        link = expanduser(self.base_dpath + '/' + self.dbname)
        ut.ensuredir(dpath)
        self.real_dpath = dpath
        try:
            self.link = ut.symlink(dpath, link, overwrite=True)
        except Exception:
            if exists(dpath):
                newpath = ut.non_existing_path(dpath, suffix='_old')
                ut.move(link, newpath)
                self.link = ut.symlink(dpath, link)

        # Load or create the deploy classifiers
        clf_dpath = ut.ensuredir((self.dpath, 'clf'))
        classifiers = pblm.ensure_deploy_classifiers(dpath=clf_dpath)
        # infr = pblm.infr
        # edges = pblm.samples.aid_pairs[0:10]
        # pblm.infr.classifiers = classifiers

        # ut.get_nonconflicting_path(dpath, suffix='_old')
        const_dials = {
            # 'oracle_accuracy' : (0.98, 1.0),
            # 'oracle_accuracy' : (0.98, .98),
            'oracle_accuracy' : (0.98, .98),
            'k_redun'         : 2,
            'max_outer_loops' : np.inf,
            # 'max_outer_loops' : 1,
        }

        sim_params = {
            'test_aids': test_aids,
            'classifiers': classifiers,
            'graph_thresh': graph_thresh,
            'rankclf_thresh': rankclf_thresh,
            'const_dials': const_dials,
        }
        self.sim_params = sim_params
        return sim_params

    @profile
    def measure_simulation(self, aug=''):
        """
        CommandLine:
            python -m ibeis Chap5.measure simulation PZ_MTEST
            python -m ibeis Chap5.measure simulation GZ_Master1
            python -m ibeis Chap5.measure simulation PZ_Master1 --show

            python -m ibeis Chap5.print_measures --db GZ_Master1 --diskshow
            python -m ibeis Chap5.print_measures --db PZ_Master1 --diskshow

        Ignore:
            >>> from ibeis.scripts.thesis import *
            >>> aug = ''
            >>> self = Chap5('GZ_Master1')
            >>> self = Chap5('PZ_MTEST')
        """
        import ibeis
        sim_params = getattr(self, 'sim_params', None)
        if sim_params is None:
            sim_params = self._setup()

        ibs = self.ibs

        classifiers = sim_params['classifiers']
        test_aids = sim_params['test_aids']
        rankclf_thresh = sim_params['rankclf_thresh']
        graph_thresh = sim_params['graph_thresh']
        const_dials = sim_params['const_dials']

        # ----------
        # Graph test
        varied_dials = {
            'enable_inference'   : True,
            'match_state_thresh' : graph_thresh,
            'name'               : 'graph'
        }
        dials = ut.dict_union(const_dials, varied_dials)
        verbose = 1
        infr1 = ibeis.AnnotInference(ibs=ibs, aids=test_aids, autoinit=True,
                                     verbose=verbose)
        infr1.enable_auto_prioritize_nonpos = True
        infr1._refresh_params['window'] = 20
        infr1._refresh_params['thresh'] = np.exp(-2)
        infr1._refresh_params['patience'] = 20

        infr1.init_simulation(classifiers=classifiers, **dials)
        infr1.init_test_mode()
        infr1.reset(state='empty')
        infr1.main_loop()

        expt_results = {}
        refresh_thresh = infr1.refresh._prob_any_remain_thresh
        graph_expt_data = {
            'real_ccs': list(infr1.nid_to_gt_cc.values()),
            'pred_ccs': list(infr1.pos_graph.connected_components()),
            'graph': infr1.graph.copy(),
            'dials': dials,
            'refresh_thresh': refresh_thresh,
            'metrics': infr1.metrics_list,
        }
        expt_results['graph'] = graph_expt_data

        pred_confusion = pd.DataFrame(infr1.test_state['confusion'])
        pred_confusion.index.name = 'real'
        pred_confusion.columns.name = 'pred'
        print('Edge confusion')
        print(pred_confusion)

        # --------
        # Rank+CLF
        varied_dials = {
            'enable_inference'   : False,
            'match_state_thresh' : rankclf_thresh,
            'name'               : 'rank+clf'
        }
        dials = ut.dict_union(const_dials, varied_dials)
        verbose = 1
        infr2 = ibeis.AnnotInference(ibs=ibs, aids=test_aids,
                                     autoinit=True, verbose=verbose)
        infr2.init_simulation(classifiers=classifiers, **dials)
        infr2.init_test_mode()
        infr2.enable_redundancy = False
        infr2.enable_autoreview = True
        infr2.reset(state='empty')

        infr2.main_loop(max_loops=1, use_refresh=False)

        verifier_expt_data = {
            'real_ccs': list(infr2.nid_to_gt_cc.values()),
            'pred_ccs': list(infr2.pos_graph.connected_components()),
            'graph': infr2.graph.copy(),
            'dials': dials,
            'refresh_thresh': refresh_thresh,
            'metrics': infr2.metrics_list,
        }
        expt_results['rank+clf'] = verifier_expt_data

        # ------------
        # Ranking test
        varied_dials = {
            'enable_inference'   : False,
            'match_state_thresh' : None,
            'name'               : 'ranking'
        }
        dials = ut.dict_union(const_dials, varied_dials)
        verbose = 1
        infr3 = ibeis.AnnotInference(ibs=ibs, aids=test_aids,
                                     autoinit=True, verbose=verbose)
        infr3.init_simulation(classifiers=None, **dials)
        infr3.init_test_mode()
        infr3.enable_redundancy = False
        infr3.enable_autoreview = False
        infr3.reset(state='empty')
        infr3.main_loop(max_loops=1, use_refresh=False)
        ranking_expt_data = {
            'real_ccs': list(infr3.nid_to_gt_cc.values()),
            'pred_ccs': list(infr3.pos_graph.connected_components()),
            'graph': infr3.graph.copy(),
            'dials': dials,
            'refresh_thresh': refresh_thresh,
            'metrics': infr3.metrics_list,
        }
        expt_results['ranking'] = ranking_expt_data

        expt_name = 'simulation' + aug
        full_fname = expt_name + ut.get_dict_hashid(const_dials)

        ut.ensuredir(self.dpath)
        ut.save_data(join(self.dpath, full_fname + '.pkl'), expt_results)
        ut.save_data(join(self.dpath, expt_name + '.pkl'), expt_results)
        self.expt_results = expt_results

        # metrics_df = pd.DataFrame.from_dict(graph_expt_data['metrics'])
        # for user, group in metrics_df.groupby('user_id'):
        #     print('actions of user = %r' % (user,))
        #     user_actions = group['action']
        #     print(ut.repr4(ut.dict_hist(user_actions), stritems=True))

        # self.draw_simulation()
        # ut.show_if_requested()
        pass

    def draw_error_graph_analysis(self):
        """
        Ignore:
            >>> from ibeis.scripts.thesis import *
            >>> self = Chap5('GZ_Master1')
        """
        import ibeis
        from ibeis.algo.graph import nx_utils as nxu

        expt_name = 'simulation'
        expt_results = ut.load_data(join(self.dpath, expt_name + '.pkl'))

        key = 'graph'
        real_ccs = expt_results[key]['real_ccs']
        pred_ccs = expt_results[key]['pred_ccs']

        delta = ut.grouping_delta(pred_ccs, real_ccs)
        # unchanged = delta['unchanged']
        splits = delta['splits']['new'] + delta['hybrid']['splits']
        merges = delta['merges']['old'] + delta['hybrid']['merges']
        splits = [s for s in splits if len(s) > 1]
        merges = [m for m in merges if len(m) > 1]

        splits = ut.sortedby(splits, [len(ut.flatten(x)) for x in splits])
        merges = ut.sortedby(merges, [len(ut.flatten(x)) for x in merges])

        splits = [ut.sortedby(ss, ut.emap(len, ss)) for ss in splits]
        merges = [ut.sortedby(ss, ut.emap(len, ss)) for ss in merges]

        graph = expt_results[key]['graph']
        if True:
            print('\nsplits = ' + ut.repr4(splits))

            print('\nmerges = ' + ut.repr4(merges))

            ignore = ['timestamp', 'num_reviews', 'confidence', 'default_priority',
                      'review_id']

            def print_edge_df(df, parts):
                if len(df):
                    order = ['truth', 'decision', 'tags', 'prob_match']
                    order = df.columns.intersection(order)
                    neworder = ut.partial_order(df.columns, order)
                    df = df.reindex_axis(neworder, axis=1)

                    df_str = df.to_string()
                    cols = ['blue', 'red', 'green', 'teal']
                    df_str = ut.highlight_multi_regex(df_str, {
                        ut.regex_or(ut.regex_word(str(a)) for a in part): col
                        for part, col in zip(parts, cols)})
                    print(df_str)
                else:
                    print(df)

            for parts in merges:
                print('\n\n')
                print('Merge Row: ' + ut.repr2(parts))
                sub = graph.subgraph(ut.flatten(parts))
                df = nxu.edge_df(graph, sub.edges(), ignore=ignore)
                print_edge_df(df, parts)

            for parts in splits:
                print('\n\n')
                print('Split Row: ' + ut.repr2(parts))
                sub = graph.subgraph(ut.flatten(parts))
                df = nxu.edge_df(graph, sub.edges(), ignore=ignore)
                print_edge_df(df, parts)

        error_aids = set(ut.total_flatten(merges) + ut.total_flatten(splits))
        err_graph = graph.subgraph(error_aids)

        if False:
            for merge in merges:
                for cc1, cc2 in ut.combinations(merge, 2):
                    x = list(nxu.edges_between(err_graph, cc1, cc2))
                    err_graph.remove_edges_from(x)

        # Find edges that were completely missed
        missing_edges = []
        for merge in merges:
            for cc1, cc2 in ut.combinations(merge, 2):
                edges = list(nxu.edges_between(err_graph, cc1, cc2))
                edges2 = []
                for e in edges:
                    d = err_graph.get_edge_data(*e)
                    if d.get('decision') in {NEGTV}:
                        edges2.append(e)
                if len(edges2) == 0:
                    missing = [(next(iter(cc1)), next(iter(cc2)))]
                    # missing = list(nxu.edge_connected_augmentation(
                    #     err_graph.subgraph(cc1.union(cc2)), k=1))
                    missing_edges.extend(missing)

        err_graph.add_edges_from(missing_edges)
        infr = ibeis.AnnotInference.from_netx(err_graph)

        infr.set_node_attrs('real_nid', {
            aid: nid for nid, cc in enumerate(real_ccs)
            for aid in cc if aid in error_aids})

        infr.set_node_attrs('pred_nid', {
            aid: nid for nid, cc in enumerate(pred_ccs)
            for aid in cc if aid in error_aids})

        infr.relabel_using_reviews()
        # infr.show(groupby='real_nid', splines='spline', fnum=1)

        edge_overrides = {
            'alpha': {
                (u, v): .05
                for (u, v, d) in infr.graph.edges(data=True)
                if d.get('decision') == NEGTV and
                (d.get('truth') == d.get('decision'))
            },
            'style': {e: '' for e in missing_edges},
            'sketch': {e: None for e in missing_edges},
            'linestyle': {e: 'dashed' for e in missing_edges},
            'linewidth': {e: 2.0 for e in missing_edges},
            'stroke': {
                (u, v): {'linewidth': 3, 'foreground': infr._error_color}
                for (u, v, d) in infr.graph.edges(data=True)
                if (d.get('truth') != d.get('decision') or d.get('truth') is None)
            },
        }

        infr.show(groupby='pred_nid', splines='spline', fnum=1,
                  simple_labels=True,
                  colorby='real_nid',
                  show_recent_review=False,
                  edge_overrides=edge_overrides)

    def print_measures(self, aug=''):
        """
        CommandLine:
            python -m ibeis Chap5.print_measures --db PZ_MTEST --diskshow
            python -m ibeis Chap5.print_measures --db GZ_Master1 --diskshow
            python -m ibeis Chap5.print_measures --db PZ_Master1 --diskshow

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> dbname = ut.get_argval('--db', default='GZ_Master1')
            >>> aug = ut.get_argval('--aug', default='')
            >>> self = Chap5(dbname)
            >>> self.print_measures(aug)
        """
        expt_name = 'simulation' + aug
        expt_results = ut.load_data(join(self.dpath, expt_name + '.pkl'))
        keys = ['ranking', 'rank+clf', 'graph']
        infos = {}
        for key in keys:
            print('!!!!!!!!!!!!')
            print('key = %r' % (key,))
            expt_data = expt_results[key]
            info = self.print_error_sizes(expt_data, allow_hist=False)
            infos[key] = info

        dfs = {}
        for key in keys:
            info = infos[key]

            table = ut.odict()

            # caseinfo = info['unchanged']
            # casetable = table['common'] = ut.odict()
            # casetable['pred # PCC']    = '-'
            # casetable['pred PCC size'] = '-'
            # casetable['real # PCC']    = caseinfo['n_real_pccs']
            # casetable['real PCC size'] = caseinfo['size_real_pccs']
            # casetable['small size']    = '-'
            # casetable['large size']    = '-'

            caseinfo = info['split']
            casetable = table['split'] = ut.odict()
            casetable['pred # PCC']    = caseinfo['n_pred_pccs']
            casetable['pred PCC size'] = caseinfo['size_pred_pccs']
            casetable['real # PCC']    = caseinfo['n_real_pccs']
            casetable['real PCC size'] = caseinfo['size_real_pccs']
            # casetable['small size']    = caseinfo['ave_small']
            # casetable['large size']    = caseinfo['ave_large']

            caseinfo = info['merge']
            casetable = table['merge'] = ut.odict()
            casetable['pred # PCC']    = caseinfo['n_pred_pccs']
            casetable['pred PCC size'] = caseinfo['size_pred_pccs']
            casetable['real # PCC']    = caseinfo['n_real_pccs']
            casetable['real PCC size'] = caseinfo['size_real_pccs']
            # casetable['small size']    = caseinfo['ave_small']
            # casetable['large size']    = caseinfo['ave_large']

            df = pd.DataFrame.from_dict(table, orient='index')
            df = df.loc[list(table.keys())]
            # df = df.rename(columns={c: '\\thead{%s}' % (c) for c in df.columns})

            print(df)
            dfs[key] = df

            text = df.to_latex(index=True, escape=True)
            import re
            text = re.sub('±...', '', text)
            # text = text.replace('±', '\pm')
            # print(text)
            top, rest = text.split('\\toprule')
            header, bot = rest.split('\\midrule')

            new_text = ''.join([
                top, '\\toprule',
                '\n{} &\multicolumn{2}{c}{pred} & \multicolumn{2}{c}{real}\\\\',
                header.replace('pred', '').replace('real', ''),
                '\\midrule',
                bot
            ])
            new_text = new_text + '\\caption{%s}' % (key,)
            print(new_text)
            print('\n')

            if 0:
                ut.render_latex_text(new_text, preamb_extra=[
                    '\\usepackage{makecell}',
                ])

        caseinfo = info['split']
        casetable = table['split'] = ut.odict()
        casetable['pred # PCC']    = caseinfo['n_pred_pccs']
        casetable['real # PCC']    = caseinfo['n_real_pccs']
        casetable['small size']    = caseinfo['ave_small']
        casetable['large size']    = caseinfo['ave_large']

        caseinfo = info['merge']
        casetable = table['merge'] = ut.odict()
        casetable['pred # PCC']    = caseinfo['n_pred_pccs']
        casetable['real # PCC']    = caseinfo['n_real_pccs']
        casetable['small size']    = caseinfo['ave_small']
        casetable['large size']    = caseinfo['ave_large']

        df = pd.DataFrame.from_dict(table, orient='index')
        df = df.loc[list(table.keys())]
        print(df)

        if 1:
            df = dfs[keys[0]].T
            for key in keys[1:]:
                df = df.join(dfs[key].T, rsuffix=' ' + key)
            df = df.T
            text = df.to_latex(index=True, escape=True,
                               column_format='l' + 'r' * 6)
            # text = re.sub('±...', '', text)
            text = text.replace('±', '\pm')
            # print(text)
            top, rest = text.split('\\toprule')
            header, rest = rest.split('\\midrule')
            body, bot = rest.split('\\bottomrule')

            body2 = body
            for key in keys:
                body2 = body2.replace(key, '')
            # Put all numbers in math mode
            pat = ut.named_field('num', '[0-9.]+(\\\\pm)?[0-9.]*')
            body2 = re.sub(pat, '$' + ut.bref_field('num') + '$', body2)

            header2 = header
            # for key in ['pred', 'real']:
            #     header2 = header2.replace(key, '')
            header2 = header2.replace('\\# PCC', '\\#')
            header2 = header2.replace('PCC size', 'size')

            import ubelt as ub

            bodychunks = []
            bodylines = body2.strip().split('\n')
            for key, chunk in zip(keys, ub.chunks(bodylines, nchunks=3)):
                part = '\n\multirow{%d}{*}{%s}\n' % (len(chunk), key,)
                part += '\n'.join(['& ' + c for c in chunk])
                bodychunks.append(part)
            body3 = '\n\\midrule'.join(bodychunks) + '\n'
            print(body3)

            # mcol2 = ['\multicolumn{2}{c}{pred} & \multicolumn{2}{c}{real}']
            latex_str = ''.join([
                top.replace('{l', '{ll'),
                # '\\hline',
                '\\toprule',
                # '\n{} & {} & ' + ' & '.join(mcol2) + ' \\\\',
                ' {} & ' + header2,
                # '\\hline',
                '\\midrule',
                body3,
                # '\\hline',
                '\\bottomrule',
                bot,
            ])
            print(latex_str)
            fname = 'error_size' + aug + '.tex'
            ut.write_to(join(self.dpath, fname), latex_str)

            ut.render_latex_text(latex_str, preamb_extra=[
                '\\usepackage{makecell}',
            ])

        if 0:
            df = dfs[keys[0]]
            for key in keys[1:]:
                df = df.join(dfs[key], rsuffix=' ' + key)
            # print(df)

            text = df.to_latex(index=True, escape=True,
                               column_format='|l|' + '|'.join(['rrrr'] * 3) + '|')
            text = re.sub('±...', '', text)
            text = text.replace('±', '\pm')
            # print(text)
            top, rest = text.split('\\toprule')
            header, bot = rest.split('\\midrule')

            mcol1 = ['\multicolumn{4}{c|}{%s}' % (key,) for key in keys]
            mcol2 = ['\multicolumn{2}{c}{pred} & \multicolumn{2}{c|}{real}'] * 3

            header3 = header
            for key in keys + ['pred', 'real']:
                header3 = header3.replace(key, '')
            # header3 = header3.replace('\\# PCC', 'num')
            header3 = header3.replace('PCC size', 'size')

            latex_str = ''.join([
                top, '\\hline',
                '\n{} & ' + ' & '.join(mcol1) + ' \\\\',
                '\n{} & ' + ' & '.join(mcol2) + ' \\\\',
                header3,
                '\\hline',
                bot.replace('bottomrule', 'hline')
            ])
            print(latex_str)

            for x in re.finditer(pat, latex_str):
                print(x)
            # ut.render_latex_text(latex_str, preamb_extra=[
            #     '\\usepackage{makecell}',
            # ])

            fname = 'error_size' + aug + '.tex'
            ut.write_to(join(self.dpath, fname), latex_str)

    def print_error_sizes(self, expt_data, allow_hist=False):

        real_ccs = expt_data['real_ccs']
        pred_ccs = expt_data['pred_ccs']
        graph = expt_data['graph']
        delta_df = ut.grouping_delta_stats(pred_ccs, real_ccs)
        print(delta_df)

        delta = ut.grouping_delta(real_ccs, pred_ccs)
        unchanged = delta['unchanged']
        splits = delta['splits']['new']
        merges = delta['merges']['old']

        # hybrids can be done by first splitting and then merging
        hybrid = delta['hybrid']
        hybrid_splits = delta['hybrid']['splits']
        hybrid_merges = delta['hybrid']['merges']

        all_merges = merges + hybrid_merges
        all_splits = splits + hybrid_splits

        def ave_size(sets):
            lens = list(map(len, sets))
            hist = ut.dict_hist(lens)
            if allow_hist and len(hist) <= 2:
                return ut.repr4(hist, nl=0)
            else:
                mu = np.mean(lens)
                sigma = np.std(lens)
                return '{:.1f}±{:.1f}'.format(mu, sigma)

        def unchanged_measures(unchanged):
            pred = true = unchanged
            ('n_real_pccs', len(true)),
            ('size_real_pccs', ave_size(true)),
            unchanged_info = ut.odict([
                ('n_pred_pccs', len(pred)),
                ('size_pred_pccs', ave_size(pred)),
                ('n_real_pccs', len(true)),
                ('size_real_pccs', ave_size(true)),
            ])
            return unchanged_info

        def get_bad_edges(ccs, bad_decision, ret_ccs=False):
            for cc1, cc2 in ut.combinations(ccs, 2):
                cc1 = frozenset(cc1)
                cc2 = frozenset(cc2)
                bad_edges = []
                cross = nxu.edges_cross(graph, cc1, cc2)
                for edge in cross:
                    d = graph.get_edge_data(*edge)
                    if d['decision'] == bad_decision:
                        if ret_ccs:
                            bad_edges.append((cc1, cc2, edge))
                        else:
                            bad_edges.append(edge)
                yield bad_edges

        def split_measures(splits):
            # Filter out non-split hybrids
            splits = [s for s in splits if len(s) > 1]
            pred = ut.lmap(ut.flatten, splits)
            true = ut.flatten(splits)
            baddies = []
            smalls = []
            larges = []
            for split in splits:
                split = ut.sortedby(split, ut.lmap(len, split))
                smalls.append((split[0]))
                larges.append((split[1]))
                b = list(get_bad_edges(split, POSTV))
                baddies.append(b)

            split_info = ut.odict([
                ('n_pred_pccs', len(pred)),
                ('size_pred_pccs', ave_size(pred)),
                ('n_real_pccs', len(true)),
                ('size_real_pccs', ave_size(true)),
                ('n_true_per_pred', ave_size(splits)),
                ('ave_small', ave_size(smalls)),
                ('ave_large', ave_size(larges)),
            ])
            return split_info

        def merge_measures(merges):
            # Filter out non-merge hybrids
            merges = [s for s in merges if len(s) > 1]
            true = ut.lmap(ut.flatten, merges)
            pred = ut.flatten(merges)
            baddies = []
            n_neg_redun = 0
            n_bad_pairs = 0
            n_bad_pccs = 0
            smalls = []
            larges = []
            for merge in merges:
                merge = ut.sortedby(merge, ut.lmap(len, merge))

                smalls.append((merge[0]))
                larges.append((merge[1]))

                b = list(get_bad_edges(merge, NEGTV))
                b2 = list(get_bad_edges(merge, NEGTV, ret_ccs=True))

                baddies.append(b)
                bad_neg_redun = max(map(len, b))
                n_bad_pairs += sum(map(any, b))
                n_bad_pccs += len(
                    set(ut.flatten(ut.take_column(ut.flatten(b2), [0, 1]))))
                if bad_neg_redun >= 2:
                    n_neg_redun += 1

            merge_info = ut.odict([
                ('n_pred_pccs', len(pred)),
                ('size_pred_pccs', ave_size(pred)),
                ('n_real_pccs', len(true)),
                ('size_real_pccs', ave_size(true)),
                ('n_true_per_pred', ave_size(merges)),
                ('ave_incon_edges', ave_size(ut.lmap(ut.flatten, baddies))),
                ('n_bad_pairs', n_bad_pairs),
                ('n_bad_pccs', n_bad_pccs),
                ('n_neg_redun', n_neg_redun),
                ('ave_small', ave_size(smalls)),
                ('ave_large', ave_size(larges)),
            ])
            return merge_info

        def hybrid_measures(hybrid):
            pred = hybrid['old']
            true = hybrid['new']
            hybrid_info = ut.odict([
                ('n_pred_pccs', len(pred)),
                ('size_pred_pccs', ave_size(pred)),
                ('n_real_pccs', len(true)),
                ('size_real_pccs', ave_size(true)),
            ])
            return hybrid_info

        # lookup = {a: n for n, aids in enumerate(hybrid['new']) for a in aids}
        # hybrid_splits = []
        # for aids in hybrid['old']:
        #     nids = ut.take(lookup, aids)
        #     split_part = list(ut.group_items(aids, nids).values())
        #     hybrid_splits.append(split_part)

        # hybrid_merge_parts = ut.flatten(hybrid_splits)
        # part_nids = [lookup[aids[0]] for aids in hybrid_merge_parts]
        # hybrid_merges = list(ut.group_items(hybrid_merge_parts,
        #                                     part_nids).values())

        if True:
            info = {
                'unchanged': unchanged_measures(unchanged),
                'split': split_measures(all_splits),
                'merge': merge_measures(all_merges),
            }
            return info

        info = {
            'unchanged': unchanged_measures(unchanged),
            'psplit': split_measures(splits),
            'pmerge': merge_measures(merges),
            'hybrid': hybrid_measures(hybrid),
            'hsplit': split_measures(hybrid_splits),
            'hmerge': merge_measures(hybrid_merges),
        }

        formater = ut.partial(
            # ut.format_multiple_paragraph_sentences,
            ut.format_single_paragraph_sentences,
            max_width=110, sentence_break=False,
            sepcolon=False
        )
        def print_measures(text, info):
            print(formater(text.format(**info)))

        split_text = ut.codeblock(
            '''
            Split cases are false positives.

            There are {n_pred_pccs} PCCs with average size {size_pred_pccs}
            that should be split into {n_real_pccs} PCCs with average size
            {size_real_pccs}.

            On average, there are {n_true_per_pred} true PCCs per predicted
            PCC.

            Within each split, the average size of the smallest PCC is
            {ave_small} and the average size of the largest PCC is {ave_large}
            '''
        )

        merge_text = ut.codeblock(
            '''
            Merges cases are false negatives.
            There are {n_pred_pccs} PCCs with average size {size_pred_pccs}
            that should be merged into {n_real_pccs} PCCs with average size
            {size_real_pccs}.

            On average, there are {n_true_per_pred} predicted PCCs per
            real PCC.

            Within each merge, the average size of the smallest PCC is
            {ave_small} and the average size of the largest PCC is
            {ave_large}

            The average number of predicted negative edges within real PCCs
            is {ave_incon_edges}.

            There are {n_bad_pairs} pairs of predicted PCCs spanning
            {n_bad_pccs} total PCCs, that have incorrect negative edges.

            There are {n_neg_redun} predicted PCCs that are incorrectly
            k-negative-redundant.
            '''
        )

        hybrid_text = ut.codeblock(
            '''
            For hybrid cases there are {n_pred_pccs} PCCs with average size
            {size_pred_pccs} that should be transformed into {n_real_pccs} PCCs
            with average size {size_real_pccs}.
            To do this, we must first split and then merge.
            '''
        )

        print('For pure split/merge cases:')
        print('------------')
        print_measures(split_text, info['psplit'])
        print('------------')
        print_measures(merge_text, info['pmerge'])
        print('------------')
        print('=============')
        print('For hybrid cases, we first split them and then merge them.')
        print_measures(hybrid_text, info['hybrid'])
        print('------------')
        print_measures(split_text, info['hsplit'])
        print('------------')
        print_measures(merge_text, info['hmerge'])
        print('------------')
        return info

    def draw_simulation(self, aug=''):
        """
        CommandLine:
            python -m ibeis Chap5.draw_simulation --db PZ_MTEST --diskshow
            python -m ibeis Chap5.draw_simulation --db GZ_Master1 --diskshow
            python -m ibeis Chap5.draw_simulation --db PZ_Master1 --diskshow

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> dbname = ut.get_argval('--db', default='GZ_Master1')
            >>> self = Chap5(dbname)
            >>> self.draw_simulation()
        """

        expt_name = 'simulation' + aug
        if not self.expt_results:
            expt_results = ut.load_data(join(self.dpath, expt_name + '.pkl'))
        else:
            expt_results = self.expt_results

        keys = ['ranking', 'rank+clf', 'graph']
        colors = ut.dzip(keys, ['red', 'orange', 'b'])
        def _metrics(col):
            return {k: ut.take_column(v['metrics'], col)
                    for k, v in expt_results.items()}

        fnum = 1

        xdatas = _metrics('n_manual')
        xmax = max(map(max, xdatas.values()))
        xpad = (1.01 * xmax) - xmax

        pnum_ = pt.make_pnum_nextgen(nSubplots=2)

        mpl.rcParams.update(TMP_RC)

        pt.figure(fnum=fnum, pnum=pnum_())
        ax = pt.gca()
        ydatas = _metrics('merge_remain')
        for key in keys:
            ax.plot(xdatas[key], ydatas[key], label=key, color=colors[key])
        ax.set_ylim(0, 1)
        ax.set_xlim(-xpad, xmax + xpad)
        ax.set_xlabel('# manual reviews')
        ax.set_ylabel('# merges remain')
        ax.legend()

        pt.figure(fnum=fnum, pnum=pnum_())
        ax = pt.gca()
        ydatas = _metrics('n_errors')
        for key in keys:
            ax.plot(xdatas[key], ydatas[key], label=key, color=colors[key])
        ax.set_ylim(0, max(map(max, ydatas.values())) * 1.01)
        ax.set_xlim(-xpad, xmax + xpad)
        ax.set_xlabel('# manual reviews')
        ax.set_ylabel('# errors')
        ax.legend()

        fig = pt.gcf()  # NOQA
        fig.set_size_inches([W, H * .75])
        pt.adjust_subplots(wspace=.25, fig=fig)

        fpath = join(self.dpath, expt_name + aug + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        if ut.get_argflag('--diskshow'):
            ut.startfile(fpath)

    def draw_refresh(self):
        """
        CommandLine:
            python -m ibeis Chap5.draw_refresh --db PZ_MTEST --show
            python -m ibeis Chap5.draw_refresh --db GZ_Master1 --diskshow
            python -m ibeis Chap5.draw_refresh --db PZ_Master1 --diskshow

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> dbname = ut.get_argval('--db', default='GZ_Master1')
            >>> self = Chap5(dbname)
            >>> self.draw_refresh()
        """

        expt_name = 'simulation'
        if not self.expt_results:
            expt_results = ut.load_data(join(self.dpath, expt_name + '.pkl'))
        else:
            expt_results = self.expt_results

        keys = ['ranking', 'rank+clf', 'graph']
        colors = ut.dzip(keys, ['red', 'orange', 'b'])
        def _metrics(col):
            return {k: ut.take_column(v['metrics'], col)
                    for k, v in expt_results.items()}

        fnum = 1

        xdatas = _metrics('n_manual')
        pnum_ = pt.make_pnum_nextgen(nSubplots=1)

        mpl.rcParams.update(TMP_RC)

        pt.figure(fnum=fnum, pnum=pnum_())
        ax = pt.gca()
        ydatas = _metrics('pprob_any')
        key = 'graph'
        ax.plot(xdatas[key], ydatas[key], label=key, color=colors[key])
        ax.set_xlabel('# manual reviews')
        ax.set_ylabel('P(T=1)')
        # ax.legend()

        fpath = join(self.dpath, 'refresh.png')
        fig = pt.gcf()  # NOQA
        fig.set_size_inches([W, H * .5])
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        if ut.get_argflag('--diskshow'):
            ut.startfile(fpath)

    def draw_simulation2(self):
        """
        CommandLine:
            python -m ibeis Chap5.draw_simulation2 --db PZ_MTEST --show
            python -m ibeis Chap5.draw_simulation2 --db GZ_Master1 --show
            python -m ibeis Chap5.draw_simulation2 --db PZ_Master1 --show

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> dbname = ut.get_argval('--db', default='GZ_Master1')
            >>> self = Chap5(dbname)
            >>> self.draw_simulation2()
            >>> ut.show_if_requested()
        """
        mpl.rcParams.update(TMP_RC)

        expt_name = 'simulation'
        if not self.expt_results:
            expt_results = ut.load_data(join(self.dpath, expt_name + '.pkl'))
        else:
            expt_results = self.expt_results
        expt_data = expt_results['graph']

        metrics_df = pd.DataFrame.from_dict(expt_data['metrics'])

        fnum = 1  # NOQA

        show_auto = 1
        if show_auto:
            xdata = metrics_df['n_decision']
            xlabel = '# decisions'
        else:
            xdata = metrics_df['n_manual']
            xlabel = '# manual reviews'

        def plot_intervals(flags, color=None, low=0, high=1):
            ax = pt.gca()
            idxs = np.where(flags)[0]
            ranges = ut.group_consecutives(idxs)
            bounds = [(min(a), max(a)) for a in ranges if len(a) > 0]
            xdata_ = xdata.values

            xs, ys = [xdata_[0]], [low]
            for a, b in bounds:
                x1, x2 = xdata_[a], xdata_[b]
                # if x1 == x2:
                x1 -= .5
                x2 += .5
                xs.extend([x1, x1, x2, x2])
                ys.extend([low, high, high, low])
            xs.append(xdata_[-1])
            ys.append(low)
            ax.fill_between(xs, ys, low, alpha=.6, color=color)

        def overlay_actions(ymax=1):
            is_correct = metrics_df['action'].map(
                lambda x: x.startswith('correct')).values
            recovering = metrics_df['recovering'].values
            is_auto = metrics_df['user_id'].map(
                lambda x: x.startswith('auto')).values
            ppos = metrics_df['pred_decision'].map(
                lambda x: x == POSTV).values
            rpos = metrics_df['true_decision'].map(
                lambda x: x == POSTV).values
            # ymax = max(metrics_df['n_errors'])

            show_pred = False

            num = 3 + (show_auto + show_pred)
            steps = np.linspace(0, 1, num + 1) * ymax
            i = -1

            if show_auto:
                i += 1
                pt.absolute_text((.2, steps[i:i + 2].mean()),
                                 'is_auto(auto=gold,manual=blue)')
                plot_intervals(is_auto, 'gold', low=steps[i], high=steps[i + 1])
                plot_intervals(~is_auto, 'blue', low=steps[i], high=steps[i + 1])

            if show_pred:
                i += 1
                pt.absolute_text((.2, steps[i:i + 2].mean()), 'pred_pos')
                plot_intervals(ppos, 'aqua', low=steps[i], high=steps[i + 1])
                # plot_intervals(~ppos, 'salmon', low=steps[i], high=steps[i + 1])

            i += 1
            pt.absolute_text((.2, steps[i:i + 2].mean()), 'real_pos')
            plot_intervals(rpos, 'lime', low=steps[i], high=steps[i + 1])
            # plot_intervals(~ppos, 'salmon', low=steps[i], high=steps[i + 1])

            i += 1
            pt.absolute_text((.2, steps[i:i + 2].mean()), 'is_error')
            # plot_intervals(is_correct, 'blue', low=steps[i], high=steps[i + 1])
            plot_intervals(~is_correct, 'red', low=steps[i], high=steps[i + 1])

            i += 1
            pt.absolute_text((.2, steps[i:i + 2].mean()), 'is_recovering')
            plot_intervals(recovering, 'orange', low=steps[i], high=steps[i + 1])

        pnum_ = pt.make_pnum_nextgen(nRows=2, nSubplots=8)

        ydatas = ut.odict([
            ('Graph',  metrics_df['merge_remain']),
        ])
        pt.multi_plot(
            xdata, ydatas, marker='', markersize=1,
            xlabel=xlabel, ylabel='# merge remaining',
            ymin=0, rcParams=TMP_RC,
            use_legend=True, fnum=1, pnum=pnum_(),
        )
        # overlay_actions(1)

        ykeys = ['n_errors']
        pt.multi_plot(
            xdata, metrics_df[ykeys].values.T,
            xlabel=xlabel, ylabel='# of errors',
            marker='', markersize=1, ymin=0, rcParams=TMP_RC,
            fnum=1, pnum=pnum_(),
            use_legend=False,
        )
        overlay_actions(max(metrics_df['n_errors']))

        pt.multi_plot(
            xdata, [metrics_df['pprob_any']],
            label_list=['P(T=1)'],
            xlabel=xlabel, ylabel='refresh criteria',
            marker='', ymin=0, ymax=1, rcParams=TMP_RC,
            fnum=1, pnum=pnum_(),
            use_legend=False,
        )
        ax = pt.gca()
        thresh = expt_data['refresh_thresh']
        ax.plot([min(xdata), max(xdata)], [thresh, thresh], '-g',
                label='refresh thresh')
        ax.legend()
        # overlay_actions(1)

        ykeys = ['n_fn', 'n_fp']
        pt.multi_plot(
            xdata, metrics_df[ykeys].values.T,
            label_list=ykeys,
            xlabel=xlabel, ylabel='# of errors',
            marker='x', markersize=1, ymin=0, rcParams=TMP_RC,
            ymax=max(metrics_df['n_errors']),
            fnum=1, pnum=pnum_(),
            use_legend=True,
        )

        xdata = metrics_df['n_manual']
        xlabel = '# manual reviews'
        ydatas = ut.odict([
            ('Graph',  metrics_df['merge_remain']),
        ])
        pt.multi_plot(
            xdata, ydatas, marker='', markersize=1,
            xlabel=xlabel, ylabel='# merge remaining',
            ymin=0, rcParams=TMP_RC,
            use_legend=True, fnum=1, pnum=pnum_(),
        )
        # overlay_actions(1)

        ykeys = ['n_errors']
        pt.multi_plot(
            xdata, metrics_df[ykeys].values.T,
            xlabel=xlabel, ylabel='# of errors',
            marker='', markersize=1, ymin=0, rcParams=TMP_RC,
            fnum=1, pnum=pnum_(),
            use_legend=False,
        )
        overlay_actions(max(metrics_df['n_errors']))

        pt.multi_plot(
            xdata, [metrics_df['pprob_any']],
            label_list=['P(T=1)'],
            xlabel=xlabel, ylabel='refresh criteria',
            marker='', ymin=0, ymax=1, rcParams=TMP_RC,
            fnum=1, pnum=pnum_(),
            use_legend=False,
        )
        ax = pt.gca()
        thresh = expt_data['refresh_thresh']
        ax.plot([min(xdata), max(xdata)], [thresh, thresh], '-g',
                label='refresh thresh')
        ax.legend()
        # overlay_actions(1)

        ykeys = ['n_fn', 'n_fp']
        pt.multi_plot(
            xdata, metrics_df[ykeys].values.T,
            label_list=ykeys,
            xlabel=xlabel, ylabel='# of errors',
            marker='x', markersize=1, ymin=0, rcParams=TMP_RC,
            ymax=max(metrics_df['n_errors']),
            fnum=1, pnum=pnum_(),
            use_legend=True,
        )

        # fpath = join(self.dpath, expt_name + '2' + '.png')
        # fig = pt.gcf()  # NOQA
        # fig.set_size_inches([W * 1.5, H * 1.1])
        # vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        # if ut.get_argflag('--diskshow'):
        #     ut.startfile(fpath)
        # fig.save_fig

        # if 1:
        #     pt.figure(fnum=fnum, pnum=(2, 2, 4))
        #     overlay_actions(ymax=1)
        pt.set_figtitle(self.dbname)


@ut.reloadable_class
class Chap4(DBInputs, IOContract):
    """
    Collect data from experiments to visualize

    TODO: redo save/loading of measurments

    Ignore:
        >>> from ibeis.scripts.thesis import *
        >>> fpath = ut.glob(ut.truepath('~/Desktop/mtest_plots'), '*.pkl')[0]
        >>> self = ut.load_data(fpath)
    """
    base_dpath = ut.truepath('~/latex/crall-thesis-2017/figures4')

    task_nice_lookup = {
        'match_state': const.REVIEW.CODE_TO_NICE,
        'photobomb_state': {
            'pb': 'Photobomb',
            'notpb': 'Not Photobomb',
        }
    }

    def _setup(self):
        r"""
        CommandLine:
            python -m ibeis Chap4._setup --db GZ_Master1

            python -m ibeis Chap4._setup --db PZ_Master1 --eval
            python -m ibeis Chap4._setup --db PZ_MTEST
            python -m ibeis Chap4._setup --db PZ_PB_RF_TRAIN

            python -m ibeis Chap4.measure_all --db PZ_PB_RF_TRAIN

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> dbname = ut.get_argval('--db', default='GZ_Master1')
            >>> self = Chap4(dbname)
            >>> self._setup()

        Ignore:
            from ibeis.scripts.thesis import *
            self = Chap4('PZ_Master1')

            from ibeis.scripts.thesis import *
            self = Chap4('PZ_PB_RF_TRAIN')

            self.ibs.print_annot_stats(aids, prefix='P')
        """
        import ibeis
        self._precollect()
        ibs = self.ibs

        if ibs.dbname == 'PZ_Master1':
            # FIND ALL PHOTOBOMB / INCOMPARABLE CASES
            if False:
                infr = ibeis.AnnotInference(ibs, aids='all')
                infr.reset_feedback('staging', apply=True)
                print(ut.repr4(infr.status()))

                pblm = script_vsone.OneVsOneProblem.from_aids(ibs, self.aids_pool)
                pblm.load_samples()
                pblm.samples.print_info()

            aids = self.aids_pool
            # infr = ibeis.AnnotInference(ibs, aids=self.aids_pool)
            # infr.reset_feedback('staging', apply=True)
            # minority_ccs = find_minority_class_ccs(infr)

            # # Need to reduce sample size for this data
            # annots = ibs.annots(self.aids_pool)
            # names = list(annots.group_items(annots.nids).values())
            # ut.shuffle(names, rng=321)
            # # Use same aids as the Chapter5 training set
            # aids = ut.flatten(names[0::2])
            # # test_aids = ut.flatten(names[1::2])

            # # Add in the minority cases
            # minority_aids = set(ut.flatten(minority_ccs))
            # aids = sorted(set(minority_aids).union(set(aids)))
        else:
            aids = self.aids_pool

        pblm = script_vsone.OneVsOneProblem.from_aids(ibs, aids)
        data_key = pblm.default_data_key
        clf_key = pblm.default_clf_key
        pblm.eval_task_keys = ['match_state', 'photobomb_state']
        pblm.eval_data_keys = [data_key]
        pblm.eval_clf_keys = [clf_key]

        if ut.get_argflag('--eval'):
            pblm.eval_task_keys = ['photobomb_state', 'match_state']
            # pblm.eval_task_keys = ['match_state']
            pblm.eval_data_keys = None
            pblm.evaluate_classifiers()
            pblm.eval_data_keys = [data_key]
        else:
            pblm.setup_evaluation()

        if False:
            pblm.infr
            pblm.load_samples()

        # pblm.evaluate_classifiers()
        ibs = pblm.infr.ibs
        pblm.samples.print_info()

        species_code = ibs.get_database_species(pblm.infr.aids)[0]
        if species_code == 'zebra_plains':
            species = 'Plains Zebras'
        if species_code == 'zebra_grevys':
            species = 'Grévy\'s Zebras'
        dbcode = '{}_{}'.format(ibs.dbname, len(pblm.samples))

        self.pblm = pblm
        self.dbcode = dbcode
        self.eval_task_keys = pblm.eval_task_keys
        self.species = species
        self.data_key = data_key
        self.clf_key = clf_key

        # RESET DPATH BASED ON SAMPLE?
        # MAYBE SYMLINK TO NEW DPATH?
        from os.path import expanduser
        dpath = expanduser(self.base_dpath + '/' + self.dbcode)
        link = expanduser(self.base_dpath + '/' + self.dbname)
        ut.ensuredir(dpath)
        self.real_dpath = dpath
        try:
            self.link = ut.symlink(dpath, link, overwrite=True)
        except Exception:
            if exists(dpath):
                newpath = ut.non_existing_path(dpath, suffix='_old')
                ut.move(link, newpath)
                self.link = ut.symlink(dpath, link)

    def measure_all(self):
        r"""
        CommandLine:
            python -m ibeis Chap4.measure_all --db PZ_PB_RF_TRAIN
            python -m ibeis Chap4.measure_all --db PZ_MTEST
            python -m ibeis Chap4.measure_all

            python -m ibeis Chap4.measure_all --db GZ_Master1

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> dbname = ut.get_argval('--db', default='PZ_MTEST')
            >>> dbnames = ut.get_argval('--dbs', type_=list, default=[dbname])
            >>> for dbname in dbnames:
            >>>     print('dbname = %r' % (dbname,))
            >>>     self = Chap4(dbname)
            >>>     self.measure_all()
        """
        self._setup()
        pblm = self.pblm

        expt_name = 'sample_info'
        results = {
            'graph': pblm.infr.graph,
            'aid_pool': self.aids_pool,
            'pblm_aids': pblm.infr.aids,
            'encoded_labels2d': pblm.samples.encoded_2d(),
            'subtasks': pblm.samples.subtasks,
            'multihist': pblm.samples.make_histogram(),
        }
        self.expt_results[expt_name] = results
        ut.save_data(join(str(self.dpath), expt_name + '.pkl'), results)

        importance = {
            task_key: pblm.feature_importance(task_key=task_key)
            for task_key in pblm.eval_task_keys
        }

        task = pblm.samples['match_state']
        scores = pblm.samples.simple_scores['score_lnbnn_1vM']
        y = task.indicator_df[task.default_class_name]
        lnbnn_xy = pd.concat([scores, y], axis=1)

        results = {
            'lnbnn_xy': lnbnn_xy,
            'task_combo_res': self.pblm.task_combo_res,
            'importance': importance,
            'data_key': self.data_key,
            'clf_key': self.clf_key,
        }
        expt_name = 'all'
        self.expt_results[expt_name] = results
        ut.save_data(join(str(self.dpath), expt_name + '.pkl'), results)

        task_key = 'match_state'
        if task_key in pblm.eval_task_keys:
            self.measure_hard_cases(task_key)

        task_key = 'photobomb_state'
        if task_key in pblm.eval_task_keys:
            self.measure_hard_cases(task_key)

        self.measure_rerank()
        self.measure_prune()

        if ut.get_argflag('--draw'):
            self.draw_all()

    def draw_all(self):
        r"""
        CommandLine:
            python -m ibeis Chap4.draw_all --db PZ_MTEST
            python -m ibeis Chap4.draw_all --db PZ_PB_RF_TRAIN
            python -m ibeis Chap4.draw_all --db GZ_Master1
            python -m ibeis Chap4.draw_all --db PZ_Master1

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> dbname = ut.get_argval('--db', default='PZ_MTEST')
            >>> dbnames = ut.get_argval('--dbs', type_=list, default=[dbname])
            >>> for dbname in dbnames:
            >>>     print('dbname = %r' % (dbname,))
            >>>     self = Chap4(dbname)
            >>>     self.draw_all()
        """
        results = self.ensure_results('all')
        eval_task_keys = set(results['task_combo_res'].keys())

        self.write_sample_info()

        task_key = 'photobomb_state'
        if task_key in eval_task_keys:
            self.write_importance(task_key)
            self.write_metrics(task_key)
            self.write_metrics2(task_key)
            self.draw_roc(task_key)
            self.draw_mcc_thresh(task_key)

        task_key = 'match_state'
        if task_key in eval_task_keys:
            self.draw_class_score_hist()
            self.draw_roc(task_key)
            self.draw_mcc_thresh(task_key)

            self.draw_wordcloud(task_key)
            self.write_importance(task_key)
            self.write_metrics(task_key)

            self.draw_rerank()

            if not ut.get_argflag('--noprune'):
                self.draw_prune()

        if not ut.get_argflag('--nodraw'):
            task_key = 'match_state'
            if task_key in eval_task_keys:
                self.draw_hard_cases(task_key)

            task_key = 'photobomb_state'
            if task_key in eval_task_keys:
                self.draw_hard_cases(task_key)

    def measure_prune(self):
        """
        >>> from ibeis.scripts.thesis import *
        >>> self = Chap4('GZ_Master1')
        >>> self = Chap4('PZ_Master1')
        >>> self = Chap4('PZ_MTEST')
        """
        # from sklearn.feature_selection import SelectFromModel
        from ibeis.scripts import clf_helpers
        if getattr(self, 'pblm', None) is None:
            self._setup()

        pblm = self.pblm
        task_key = pblm.primary_task_key
        data_key = pblm.default_data_key
        clf_key = pblm.default_clf_key

        featinfo = vt.AnnotPairFeatInfo(pblm.samples.X_dict[data_key])
        print(featinfo.get_infostr())

        labels = pblm.samples.subtasks[task_key]
        # X = pblm.samples.X_dict[data_key]

        feat_dims = pblm.samples.X_dict[data_key].columns.tolist()
        n_orig = len(feat_dims)
        n_dims = []
        reports = []
        sub_reports = []
        mdis_list = []

        prune_rate = 1
        min_feats = 1

        n_steps_needed = int(np.ceil((n_orig - min_feats) / prune_rate))
        prog = ub.ProgIter(range(n_steps_needed), label='prune')
        for _ in prog:
            prog.ensure_newline()
            clf_list, res_list = pblm._train_evaluation_clf(task_key, data_key,
                                                            clf_key, feat_dims)
            combo_res = clf_helpers.ClfResult.combine_results(res_list, labels)
            rs = [res.extended_clf_report(verbose=0) for res in res_list]
            report = combo_res.extended_clf_report(verbose=0)

            # Measure mean decrease in impurity
            clf_mdi = np.array(
                [clf_.feature_importances_ for clf_ in clf_list])
            mean_mdi = ut.dzip(feat_dims, np.mean(clf_mdi, axis=0))

            # Record state
            n_dims.append(len(feat_dims))
            reports.append(report)
            sub_reports.append(rs)
            mdis_list.append(mean_mdi)

            # remove the worst features
            sorted_featdims = ub.argsort(mean_mdi)
            n_have = len(sorted_featdims)
            n_remove = (n_have - max(n_have - prune_rate, min_feats))
            worst_features = sorted_featdims[0:n_remove]
            for f in worst_features:
                feat_dims.remove(f)

        results = {
            'n_dims': n_dims,
            'reports': reports,
            'sub_reports': sub_reports,
            'mdis_list': mdis_list,
        }
        expt_name = 'prune'
        self.expt_results[expt_name] = results
        ut.save_data(join(str(self.dpath), expt_name + '.pkl'), results)

    def draw_prune(self):
        """
        CommandLine:
            python -m ibeis Chap4.draw importance GZ_Master1

            python -m ibeis Chap4.draw importance PZ_Master1 photobomb_state
            python -m ibeis Chap4.draw importance PZ_Master1 match_state

            python -m ibeis Chap4.draw prune GZ_Master1,PZ_Master1
            python -m ibeis Chap4.draw prune PZ_Master1

        >>> from ibeis.scripts.thesis import *
        >>> self = Chap4('PZ_Master1')
        >>> self = Chap4('GZ_Master1')
        >>> self = Chap4('PZ_MTEST')
        """

        task_key = 'match_state'
        expt_name = 'prune'
        results = self.ensure_results(expt_name)

        n_dims = results['n_dims']
        mdis_list = results['mdis_list']
        sub_reports = results['sub_reports']

        # mccs = [r['mcc'] for r in reports]
        # mccs2 = np.array([[r['mcc'] for r in rs] for rs in sub_reports])
        # pos_mccs = np.array([[r['metrics']['mcc'][POSTV] for r in rs]
        # for rs in sub_reports])
        ave_mccs = np.array([[r['metrics']['mcc']['ave/sum'] for r in rs]
                             for rs in sub_reports])

        import plottool as pt

        mpl.rcParams.update(TMP_RC)
        fig = pt.figure(fnum=1, doclf=True)
        pt.multi_plot(n_dims, {'mean': ave_mccs.mean(axis=1)},
                      rcParams=TMP_RC,
                      marker='',
                      force_xticks=[min(n_dims)],
                      # num_xticks=5,
                      ylabel='MCC',
                      xlabel='# feature dimensions',
                      ymin=.5,
                      ymax=1, xmin=1, xmax=n_dims[0], fnum=1, use_legend=False)
        ax = pt.gca()
        ax.invert_xaxis()
        fig.set_size_inches([W / 2, H])
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))

        # Find the point at which accuracy starts to fall
        u = ave_mccs.mean(axis=1)
        # middle = ut.take_around_percentile(u, .5, len(n_dims) // 2.2)
        # thresh = middle.mean() - (middle.std() * 6)
        # print('thresh = %r' % (thresh,))
        # idx = np.where(u < thresh)[0][0]
        idx = u.argmax()

        fig = pt.figure(fnum=2)
        n_to_mid = ut.dzip(n_dims, mdis_list)
        pruned_importance = n_to_mid[n_dims[idx]]
        pt.wordcloud(pruned_importance, ax=fig.axes[0])
        fname = 'wc_{}_pruned.png'.format(task_key)
        fig_fpath = join(str(self.dpath), fname)
        vt.imwrite(fig_fpath, pt.render_figure_to_image(fig, dpi=DPI))

        vals = pruned_importance.values()
        items = pruned_importance.items()
        top_dims = ut.sortedby(items, vals)[::-1]
        lines = []
        num_top = 10
        for k, v in top_dims[:num_top]:
            k = feat_alias(k)
            k = k.replace('_', '\\_')
            lines.append('{} & {:.4f} \\\\'.format(k, v))
        latex_str = '\n'.join(ut.align_lines(lines, '&'))

        increase = u[idx] - u[0]

        print(latex_str)
        print()
        extra_ = ut.codeblock(
            r'''
            \begin{{table}}[h]
                \centering
                \caption{{Pruned top {}/{} dimensions for {} increases MCC by {:.4f}}}
                \begin{{tabular}}{{lr}}
                    \toprule
                    dimension & importance \\
                    \midrule
                    {}
                    \bottomrule
                \end{{tabular}}
            \end{{table}}
            '''
        ).format(num_top, len(pruned_importance), task_key.replace('_', '-'),
                 increase, latex_str)
        # topinfo = vt.AnnotPairFeatInfo(list(pruned_importance.keys()))

        fname = 'pruned_feat_importance_{}'.format(task_key)
        fpath = ut.render_latex(extra_, dpath=self.dpath, fname=fname)
        ut.write_to(join(str(self.dpath), fname + '.tex'), latex_str)

        print(ut.repr4(ut.sort_dict(n_to_mid[n_dims[idx]], 'vals', reverse=True)))
        print(ut.repr4(ut.sort_dict(n_to_mid[n_dims[-1]], 'vals', reverse=True)))

    def measure_rerank(self):
        """
            >>> from ibeis.scripts.thesis import *
            >>> defaultdb = 'PZ_Master1'
            >>> defaultdb = 'GZ_Master1'
            >>> self = Chap4(defaultdb)
            >>> self._setup()
            >>> self.measure_rerank()
        """
        if getattr(self, 'pblm', None) is None:
            self._setup()

        pblm = self.pblm
        infr = pblm.infr
        ibs = pblm.infr.ibs

        # NOTE: this is not the aids_pool for PZ_Master1
        aids = pblm.infr.aids

        qaids, daids_list, info_list = Sampler._varied_inputs(ibs, aids)

        if pblm.hyper_params['vsone_kpts']['augment_orientation']:
            # HACK
            cfgdict = {
                'query_rotation_heuristic': True,
            }
        else:
            cfgdict = {}
        daids = daids_list[0]
        info = info_list[0]

        # Execute the ranking algorithm
        qaids = sorted(qaids)
        daids = sorted(daids)
        qreq_ = ibs.new_query_request(qaids, daids, cfgdict=cfgdict)
        cm_list = qreq_.execute()
        cm_list = [cm.extend_results(qreq_) for cm in cm_list]

        # Measure LNBNN rank probabilities
        top = 20
        rerank_pairs = []
        for cm in cm_list:
            pairs = [infr.e_(cm.qaid, daid) for daid in cm.get_top_aids(top)]
            rerank_pairs.extend(pairs)
        rerank_pairs = list(set(rerank_pairs))

        probs = pblm.predict_proba_evaluation(infr, rerank_pairs)['match_state']
        pos_probs = probs[POSTV]

        clf_name_ranks = []
        lnbnn_name_ranks = []
        infr = pblm.infr
        for cm in cm_list:
            daids = cm.get_top_aids(top)
            edges = [infr.e_(cm.qaid, daid) for daid in daids]
            dnids = cm.dnid_list[ut.take(cm.daid2_idx, daids)]
            scores = pos_probs.loc[edges].values

            sortx = np.argsort(scores)[::-1]
            clf_ranks = np.where(cm.qnid == dnids[sortx])[0]
            if len(clf_ranks) == 0:
                clf_rank = len(cm.unique_nids) - 1
            else:
                clf_rank = clf_ranks[0]
            lnbnn_rank = cm.get_name_ranks([cm.qnid])[0]
            clf_name_ranks.append(clf_rank)
            lnbnn_name_ranks.append(lnbnn_rank)

        bins = np.arange(len(qreq_.dnids))
        hist = np.histogram(lnbnn_name_ranks, bins=bins)[0]
        lnbnn_cdf = (np.cumsum(hist) / sum(hist))

        bins = np.arange(len(qreq_.dnids))
        hist = np.histogram(clf_name_ranks, bins=bins)[0]
        clf_cdf = (np.cumsum(hist) / sum(hist))

        results = [
            (lnbnn_cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict})),
            (clf_cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict})),
        ]
        expt_name = 'rerank'
        self.expt_results[expt_name] = results
        ut.save_data(join(str(self.dpath), expt_name + '.pkl'), results)

    def measure_hard_cases(self, task_key):
        """
        Find a failure case for each class

        CommandLine:
            python -m ibeis Chap4.measure hard_cases GZ_Master1 match_state
            python -m ibeis Chap4.measure hard_cases GZ_Master1 photobomb_state
            python -m ibeis Chap4.draw hard_cases GZ_Master1 match_state
            python -m ibeis Chap4.draw hard_cases GZ_Master1 photobomb_state

            python -m ibeis Chap4.measure hard_cases PZ_Master1 match_state
            python -m ibeis Chap4.measure hard_cases PZ_Master1 photobomb_state
            python -m ibeis Chap4.draw hard_cases PZ_Master1 match_state
            python -m ibeis Chap4.draw hard_cases PZ_Master1 photobomb_state

            python -m ibeis Chap4.measure hard_cases PZ_MTEST match_state
            python -m ibeis Chap4.draw hard_cases PZ_MTEST photobomb_state

        Ignore:
            >>> task_key = 'match_state'
            >>> task_key = 'photobomb_state'
            >>> from ibeis.scripts.thesis import *
            >>> self = Chap4('GZ_Master1')
            >>> self._setup()
        """
        if getattr(self, 'pblm', None) is None:
            print('Need to setup before measuring hard cases')
            self._setup()
        print('Measuring hard cases')

        pblm = self.pblm

        front = mid = back = 8

        res = pblm.task_combo_res[task_key][self.clf_key][self.data_key]

        print('task_key = %r' % (task_key,))
        if task_key == 'photobomb_state':
            method = 'max-mcc'
            method = res.get_thresholds('mcc', 'maximize')
            print('Using thresholds: ' + ut.repr4(method))
        else:
            method = 'argmax'
            print('Using argmax')

        case_df = res.hardness_analysis(pblm.samples, pblm.infr, method=method)
        # group = case_df.sort_values(['real_conf', 'easiness'])
        case_df = case_df.sort_values(['easiness'])

        # failure_cases = case_df[(case_df['real_conf'] > 0) & case_df['failed']]
        failure_cases = case_df[case_df['failed']]
        if len(failure_cases) == 0:
            print('No reviewed failures exist. Do pblm.qt_review_hardcases')

        print('There are {} failure cases'.format(len(failure_cases)))
        print('With average hardness {}'.format(
            ut.repr2(ut.stats_dict(failure_cases['hardness']), strkeys=True,
                     precision=2)))

        cases = []
        for (pred, real), group in failure_cases.groupby(('pred', 'real')):

            group = group.sort_values(['easiness'])
            flags = ut.flag_percentile_parts(group['easiness'], front, mid, back)
            subgroup = group[flags]

            print('Selected {} r({})-p({}) cases'.format(
                len(subgroup), res.class_names[real], res.class_names[pred]
            ))
            # ut.take_percentile_parts(group['easiness'], front, mid, back)

            # Prefer examples we have manually reviewed before
            # group = group.sort_values(['real_conf', 'easiness'])
            # subgroup = group[0:num_top]

            for idx, case in subgroup.iterrows():
                edge = tuple(ut.take(case, ['aid1', 'aid2']))
                cases.append({
                    'edge': edge,
                    'real': res.class_names[case['real']],
                    'pred': res.class_names[case['pred']],
                    'failed': case['failed'],
                    'easiness': case['easiness'],
                    'real_conf': case['real_conf'],
                    'probs': res.probs_df.loc[edge].to_dict(),
                    'edge_data': pblm.infr.get_edge_data(edge),
                })

        print('Selected %d cases in total' % (len(cases)))

        # Augment cases with their one-vs-one matches
        infr = pblm.infr
        data_key = self.data_key
        config = pblm.feat_construct_info[data_key][0]['match_config']
        edges = [case['edge'] for case in cases]
        matches = infr._exec_pairwise_match(edges, config)

        def _prep_annot(annot):
            # Load data needed for plot into annot dictionary
            annot['aid']
            annot['rchip']
            annot['kpts']
            # Cast the lazy dict to a real one
            return {k: annot[k] for k in annot.evaluated_keys()}

        for case, match in zip(cases, matches):
            # store its chip fpath and other required info
            match.annot1 = _prep_annot(match.annot1)
            match.annot2 = _prep_annot(match.annot2)
            case['match'] = match

        fpath = join(str(self.dpath), task_key + '_hard_cases.pkl')
        ut.save_data(fpath, cases)
        print('Hard case space on disk: {}'.format(ut.get_file_nBytes_str(fpath)))

        # if False:
        #     ybin_df = res.target_bin_df
        #     flags = ybin_df['pb'].values
        #     pb_edges = ybin_df[flags].index.tolist()

        #     matches = infr._exec_pairwise_match(pb_edges, config)
        #     prefix = 'training_'

        #     subdir = 'temp_cases_{}'.format(task_key)
        #     dpath = join(str(self.dpath), subdir)
        #     ut.ensuredir(dpath)

        #     tbl = pblm.infr.ibs.db.get_table_as_pandas('annotmatch')
        #     tagged_tbl = tbl[~pd.isnull(tbl['annotmatch_tag_text']).values]
        #     ttext = tagged_tbl['annotmatch_tag_text']
        #     flags = ['photobomb' in t.split(';') for t in ttext]
        #     pb_table = tagged_tbl[flags]
        #     am_pb_edges = set(
        #         ut.estarmap(infr.e_, zip(pb_table.annot_rowid1.tolist(),
        #                                  pb_table.annot_rowid2.tolist())))

        #     # missing = am_pb_edges - set(pb_edges)
        #     # matches = infr._exec_pairwise_match(missing, config)
        #     # prefix = 'missing_'

        #     # infr.relabel_using_reviews()
        #     # infr.apply_nondynamic_update()

        #     # infr.verbose = 100
        #     # for edge in missing:
        #     #     print(edge[0] in infr.aids)
        #     #     print(edge[1] in infr.aids)

        #     # fix = [
        #     #     (1184, 1185),
        #     #     (1376, 1378),
        #     #     (1377, 1378),
        #     # ]

        #     #     fb = infr.current_feedback(edge).copy()
        #     #     fb = ut.dict_subset(fb, ['decision', 'tags', 'confidence'],
        #     #                         default=None)
        #     #     fb['user_id'] = 'jon_fixam'
        #     #     fb['confidence'] = 'pretty_sure'
        #     #     fb['tags'] += ['photobomb']
        #     #     infr.add_feedback(edge, **fb)

        #     for c, match in enumerate(ut.ProgIter(matches)):
        #         edge = match.annot1['aid'], match.annot2['aid']

        #         fig = pt.figure(fnum=1, clf=True)
        #         ax = pt.gca()
        #         # Draw with feature overlay
        #         match.show(ax, vert=False, heatmask=True, show_lines=True,
        #                    show_ell=False, show_ori=False, show_eig=False,
        #                    line_lw=1, line_alpha=.1,
        #                    modifysize=True)
        #         fname = prefix + '_'.join(ut.emap(str, edge))
        #         ax.set_xlabel(fname)
        #         fpath = join(str(dpath), fname + '.jpg')
        #         vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        #     # visualize real photobomb cases
        return cases

    def draw_hard_cases(self, task_key):
        """
        draw hard cases with and without overlay

        python -m ibeis Chap4.draw hard_cases GZ_Master1 match_state
        python -m ibeis Chap4.draw hard_cases PZ_Master1 match_state
        python -m ibeis Chap4.draw hard_cases PZ_Master1 photobomb_state
        python -m ibeis Chap4.draw hard_cases GZ_Master1 photobomb_state



            >>> from ibeis.scripts.thesis import *
            >>> self = Chap4('PZ_MTEST')
            >>> task_key = 'match_state'
            >>> self.draw_hard_cases(task_key)
        """
        cases = self.ensure_results(task_key + '_hard_cases')
        print('Loaded {} {} hard cases'.format(len(cases), task_key))

        subdir = 'cases_{}'.format(task_key)
        dpath = join(str(self.dpath), subdir)
        # ut.delete(dpath)
        ut.ensuredir(dpath)
        code_to_nice = self.task_nice_lookup[task_key]

        mpl.rcParams.update(TMP_RC)

        pz_gt_errors = {  # NOQA
            # The true state of these pairs are:
            NEGTV: [
                (239, 3745),
                (484, 519),
                (802, 803),
            ],
            INCMP: [
                (4652, 5245),
                (4405, 5245),
                (4109, 5245),
                (16192, 16292),
            ],
            POSTV: [
                (6919, 7192),
            ]
        }

        prog = ut.ProgIter(cases, 'draw {} hard case'.format(task_key),
                           bs=False)
        for case in prog:
            aid1, aid2 = case['edge']
            match = case['match']
            real_name, pred_name = case['real'], case['pred']
            real_nice, pred_nice = ut.take(code_to_nice, [real_name, pred_name])
            fname = 'fail_{}_{}_{}_{}'.format(real_name, pred_name, aid1, aid2)
            # Build x-label
            _probs = case['probs']
            probs = ut.odict((v, _probs[k])
                             for k, v in code_to_nice.items()
                             if k in _probs)
            probstr = ut.repr2(probs, precision=2, strkeys=True, nobr=True)
            xlabel = 'real={}, pred={},\n{}'.format(real_nice, pred_nice,
                                                    probstr)
            fig = pt.figure(fnum=1000, clf=True)
            ax = pt.gca()
            # Draw with feature overlay
            match.show(ax, vert=False, heatmask=True,
                       show_lines=False,
                       # show_lines=True, line_lw=1, line_alpha=.1,
                       # ell_alpha=.3,
                       show_ell=False, show_ori=False, show_eig=False,
                       modifysize=True)
            ax.set_xlabel(xlabel)
            # ax.get_xaxis().get_label().set_fontsize(24)
            ax.get_xaxis().get_label().set_fontsize(24)

            fpath = join(str(dpath), fname + '.jpg')
            vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))

    def write_metrics2(self, task_key='match_state'):
        """
        CommandLine:
            python -m ibeis Chap4.draw metrics PZ_PB_RF_TRAIN match_state
            python -m ibeis Chap4.draw metrics2 PZ_Master1 photobomb_state
            python -m ibeis Chap4.draw metrics2 GZ_Master1 photobomb_state

            python -m ibeis Chap4.draw metrics2 GZ_Master1 photobomb_state
        """
        results = self.ensure_results('all')
        task_combo_res = results['task_combo_res']
        data_key = results['data_key']
        clf_key = results['clf_key']

        res = task_combo_res[task_key][clf_key][data_key]

        from ibeis.scripts import sklearn_utils
        threshes = res.get_thresholds('mcc', 'max')
        y_pred = sklearn_utils.predict_from_probs(res.probs_df, threshes,
                                                  force=True)
        y_true = res.target_enc_df

        # pred_enc = res.clf_probs.argmax(axis=1)
        # y_pred = pred_enc
        res.augment_if_needed()
        sample_weight = res.sample_weight
        target_names = res.class_names

        report = sklearn_utils.classification_report2(
            y_true, y_pred, target_names, sample_weight, verbose=False)
        metric_df = report['metrics']
        confusion_df = report['confusion']

        print(metric_df)
        print(confusion_df)

        # df = self.task_confusion[task_key]
        df = confusion_df
        df = df.rename_axis(self.task_nice_lookup[task_key], 0)
        df = df.rename_axis(self.task_nice_lookup[task_key], 1)
        df.index.name = None
        df.columns.name = None
        # import utool
        # utool.embed()

        latex_str = df.to_latex(
            float_format=lambda x: '' if np.isnan(x) else str(int(x)),
        )
        sum_pred = df.index[-1]
        sum_real = df.columns[-1]
        latex_str = latex_str.replace(sum_pred, r'$\sum$ predicted')
        latex_str = latex_str.replace(sum_real, r'$\sum$ real')
        # latex_str = latex_str.replace(sum_pred, r'$\textstyle\sum$ predicted')
        # latex_str = latex_str.replace(sum_real, r'$\textstyle\sum$ real')
        colfmt = '|l|' + 'r' * (len(df) - 1) + '|l|'
        newheader = '\\begin{tabular}{%s}' % (colfmt,)
        latex_str = '\n'.join([newheader] + latex_str.split('\n')[1:])
        lines = latex_str.split('\n')
        lines = lines[0:-4] + ['\\midrule'] + lines[-4:]
        latex_str = '\n'.join(lines)
        latex_str = latex_str.replace('midrule', 'hline')
        latex_str = latex_str.replace('toprule', 'hline')
        latex_str = latex_str.replace('bottomrule', 'hline')
        confusion_tex = latex_str

        df = metric_df
        # df = self.task_metrics[task_key]
        df = df.rename_axis(self.task_nice_lookup[task_key], 0)
        df = df.drop(['markedness', 'bookmaker'], axis=1)
        df.index.name = None
        df.columns.name = None
        df['support'] = df['support'].astype(np.int)
        latex_str = df.to_latex(
            float_format=lambda x: '%.2f' % (x)
        )
        lines = latex_str.split('\n')
        lines = lines[0:-4] + ['\\midrule'] + lines[-4:]
        latex_str = '\n'.join(lines)
        import re
        latex_str = re.sub(' -0.00 ', '  0.00 ', latex_str)
        metrics_tex = latex_str

        print(confusion_tex)
        print(metrics_tex)

        dpath = str(self.dpath)
        confusion_fname = 'confusion2_{}'.format(task_key)
        metrics_fname = 'eval_metrics2_{}'.format(task_key)

        ut.write_to(join(dpath, confusion_fname + '.tex'), confusion_tex)
        ut.write_to(join(dpath, metrics_fname + '.tex'), metrics_tex)

        fpath1 = ut.render_latex(confusion_tex, dpath=dpath,
                                 fname=confusion_fname)
        fpath2 = ut.render_latex(metrics_tex, dpath=dpath, fname=metrics_fname)
        return fpath1, fpath2

    def write_metrics(self, task_key='match_state'):
        """
        CommandLine:
            python -m ibeis Chap4.draw metrics PZ_PB_RF_TRAIN match_state
            python -m ibeis Chap4.draw metrics GZ_Master1 photobomb_state

            python -m ibeis Chap4.draw metrics GZ_Master1 photobomb_state

        Example:
            >>> from ibeis.scripts.thesis import *
            >>> kwargs = ut.argparse_funckw(Chap4.write_metrics)
            >>> defaultdb = 'GZ_Master1'
            >>> defaultdb = 'PZ_PB_RF_TRAIN'
            >>> defaultdb = 'PZ_MTEST'
            >>> #task_key = kwargs['task_key']
            >>> task_key = ut.get_argval('--task-key', default='match_state')
            >>> dbname = ut.get_argval('--db', default=defaultdb)
            >>> self = Chap4(dbname)
            >>> self.write_metrics(task_key)
        """
        results = self.ensure_results('all')
        task_combo_res = results['task_combo_res']
        data_key = results['data_key']
        clf_key = results['clf_key']

        res = task_combo_res[task_key][clf_key][data_key]
        res.augment_if_needed()
        pred_enc = res.clf_probs.argmax(axis=1)
        y_pred = pred_enc
        y_true = res.y_test_enc
        sample_weight = res.sample_weight
        target_names = res.class_names

        from ibeis.scripts import sklearn_utils
        report = sklearn_utils.classification_report2(
            y_true, y_pred, target_names, sample_weight, verbose=False)
        metric_df = report['metrics']
        confusion_df = report['confusion']

        print(metric_df)
        print(confusion_df)

        # df = self.task_confusion[task_key]
        df = confusion_df
        df = df.rename_axis(self.task_nice_lookup[task_key], 0)
        df = df.rename_axis(self.task_nice_lookup[task_key], 1)
        df.index.name = None
        df.columns.name = None
        # import utool
        # utool.embed()

        latex_str = df.to_latex(
            float_format=lambda x: '' if np.isnan(x) else str(int(x)),
        )
        sum_pred = df.index[-1]
        sum_real = df.columns[-1]
        latex_str = latex_str.replace(sum_pred, r'$\sum$ predicted')
        latex_str = latex_str.replace(sum_real, r'$\sum$ real')
        # latex_str = latex_str.replace(sum_pred, r'$\textstyle\sum$ predicted')
        # latex_str = latex_str.replace(sum_real, r'$\textstyle\sum$ real')
        colfmt = '|l|' + 'r' * (len(df) - 1) + '|l|'
        newheader = '\\begin{tabular}{%s}' % (colfmt,)
        latex_str = '\n'.join([newheader] + latex_str.split('\n')[1:])
        lines = latex_str.split('\n')
        lines = lines[0:-4] + ['\\midrule'] + lines[-4:]
        latex_str = '\n'.join(lines)
        latex_str = latex_str.replace('midrule', 'hline')
        latex_str = latex_str.replace('toprule', 'hline')
        latex_str = latex_str.replace('bottomrule', 'hline')
        confusion_tex = latex_str

        df = metric_df
        # df = self.task_metrics[task_key]
        df = df.rename_axis(self.task_nice_lookup[task_key], 0)
        df = df.drop(['markedness', 'bookmaker'], axis=1)
        df.index.name = None
        df.columns.name = None
        df['support'] = df['support'].astype(np.int)
        latex_str = df.to_latex(
            float_format=lambda x: '%.2f' % (x)
        )
        lines = latex_str.split('\n')
        lines = lines[0:-4] + ['\\midrule'] + lines[-4:]
        latex_str = '\n'.join(lines)
        import re
        latex_str = re.sub(' -0.00 ', '  0.00 ', latex_str)
        metrics_tex = latex_str

        print(confusion_tex)
        print(metrics_tex)

        dpath = str(self.dpath)
        confusion_fname = 'confusion_{}'.format(task_key)
        metrics_fname = 'eval_metrics_{}'.format(task_key)

        ut.write_to(join(dpath, confusion_fname + '.tex'), confusion_tex)
        ut.write_to(join(dpath, metrics_fname + '.tex'), metrics_tex)

        fpath1 = ut.render_latex(confusion_tex, dpath=dpath,
                                 fname=confusion_fname)
        fpath2 = ut.render_latex(metrics_tex, dpath=dpath, fname=metrics_fname)
        return fpath1, fpath2

    def write_sample_info(self):
        results = self.ensure_results('sample_info')
        # results['aid_pool']
        # results['encoded_labels2d']
        # results['multihist']
        import ibeis
        infr = ibeis.AnnotInference.from_netx(results['graph'])
        info = ut.odict()
        info['n_names'] = infr.pos_graph.number_of_components(),
        info['n_aids'] = len(results['pblm_aids']),
        info['known_n_incomparable'] = infr.incomp_graph.number_of_edges()
        subtasks = results['subtasks']

        task = subtasks['match_state']
        flags = (task.encoded_df == task.class_names.tolist().index(INCMP))
        incomp_edges = task.encoded_df[flags.values].index.tolist()
        nid_edges = [infr.pos_graph.node_labels(*e) for e in incomp_edges]
        nid_edges = vt.ensure_shape(np.array(nid_edges), (None, 2))

        n_true = nid_edges.T[0] == nid_edges.T[1]
        info['incomp_info'] = {
            'inside_pcc': n_true.sum(),
            'betweeen_pcc': (~n_true).sum(),
        }

        for task_key, task in subtasks.items():
            info[task_key + '_hist'] = task.make_histogram()
        info_str = ut.repr4(info)
        fname = 'sample_info.txt'
        ut.write_to(join(str(self.dpath), fname), info_str)

    def write_importance(self, task_key):
        """
        python -m ibeis Chap4.draw importance GZ_Master1 match_state
        python -m ibeis Chap4.draw importance GZ_Master1 photobomb_state

        python -m ibeis Chap4.draw importance PZ_Master1 match_state
        python -m ibeis Chap4.draw importance PZ_Master1 photobomb_state
        """
        # Print info for latex table
        results = self.ensure_results('all')
        importances = results['importance'][task_key]
        vals = importances.values()
        items = importances.items()
        top_dims = ut.sortedby(items, vals)[::-1]
        lines = []
        num_top = 10
        for k, v in top_dims[:num_top]:
            k = feat_alias(k)
            k = k.replace('_', '\\_')
            lines.append('{} & {:.4f} \\\\'.format(k, v))
        latex_str = '\n'.join(ut.align_lines(lines, '&'))

        fname = 'feat_importance_{}'.format(task_key)

        print('TOP {} importances for {}'.format(num_top, task_key))
        print('# of dimensions: %d' % (len(importances)))
        print(latex_str)
        print()
        extra_ = ut.codeblock(
            r'''
            \begin{{table}}[h]
                \centering
                \caption{{Top {}/{} dimensions for {}}}
                \begin{{tabular}}{{lr}}
                    \toprule
                    dimension & importance \\
                    \midrule
                    {}
                    \bottomrule
                \end{{tabular}}
            \end{{table}}
            '''
        ).format(num_top, len(importances), task_key.replace('_', '-'), latex_str)

        fpath = ut.render_latex(extra_, dpath=self.dpath, fname=fname)
        ut.write_to(join(str(self.dpath), fname + '.tex'), latex_str)
        return fpath

    def measure_thresh(self, pblm):
        task_key = 'match_state'
        res = pblm.task_combo_res[task_key][self.clf_key][self.data_key]
        infr = pblm.infr

        truth_colors = infr._get_truth_colors()

        cfms = res.confusions(POSTV)
        fig = pt.figure(fnum=1, doclf=True)  # NOQA
        ax = pt.gca()
        ax.plot(cfms.thresholds, cfms.n_fp, label='positive', color=truth_colors[POSTV])

        cfms = res.confusions(NEGTV)
        ax.plot(cfms.thresholds, cfms.n_fp, label='negative', color=truth_colors[NEGTV])

        # cfms = res.confusions(INCMP)
        # if len(cfms.thresholds) == 1:
        #     cfms.thresholds = [0, 1]
        #     cfms.n_fp = np.array(cfms.n_fp.tolist() * 2)
        # ax.plot(cfms.thresholds, cfms.n_fp, label='incomparable',
        #         color=pt.color_funcs.darken_rgb(truth_colors[INCMP], .15))
        ax.set_xlabel('thresholds')
        ax.set_ylabel('n_fp')

        ax.set_ylim(0, 20)
        ax.legend()

        cfms.plot_vs('fpr', 'thresholds')

    def _draw_score_hist(self, freqs, xlabel, fnum):
        """ helper """
        bins, freq0, freq1 = ut.take(freqs, ['bins', 'neg_freq', 'pos_freq'])
        width = np.diff(bins)[0]
        xlim = (bins[0] - (width / 2), bins[-1] + (width / 2))
        fig = pt.multi_plot(
            bins, (freq0, freq1), label_list=('negative', 'positive'),
            color_list=(pt.FALSE_RED, pt.TRUE_BLUE),
            kind='bar', width=width, alpha=.7, edgecolor='none',
            xlabel=xlabel, ylabel='frequency', fnum=fnum, pnum=(1, 1, 1),
            rcParams=TMP_RC, stacked=True,
            ytickformat='%.2f', xlim=xlim,
            # title='LNBNN positive separation'
        )
        pt.adjust_subplots(top=.8, bottom=.2, left=.12, right=.9)
        fig.set_size_inches([W, H])
        return fig

    def draw_rerank(self):
        mpl.rcParams.update(TMP_RC)

        expt_name = 'rerank'
        results = self.ensure_results(expt_name)

        cdfs, infos = list(zip(*results))
        lnbnn_cdf = cdfs[0]
        clf_cdf = cdfs[1]
        fig = pt.figure(fnum=1)
        plot_cmcs([lnbnn_cdf, clf_cdf], ['ranking', 'rank+clf'], fnum=1)
        fig.set_size_inches([W, H * .6])
        qsizes = ut.take_column(infos, 'qsize')
        dsizes = ut.take_column(infos, 'dsize')
        assert ut.allsame(qsizes) and ut.allsame(dsizes)
        nonvaried_text = 'qsize={}, dsize={}'.format(qsizes[0], dsizes[0])
        pt.relative_text('lowerleft', nonvaried_text, ax=pt.gca())

        fpath = join(str(self.dpath), expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        if ut.get_argflag('--diskshow'):
            ut.startfile(fpath)
        return fpath

    def draw_class_score_hist(self):
        """ Plots distribution of positive and negative scores """
        task_key = 'match_state'

        results = self.ensure_results('all')
        task_combo_res = results['task_combo_res']
        data_key = results['data_key']
        clf_key = results['clf_key']

        res = task_combo_res[task_key][clf_key][data_key]

        y = res.target_bin_df[POSTV]
        scores = res.probs_df[POSTV]
        bins = np.linspace(0, 1, 100)
        pos_freq = np.histogram(scores[y], bins)[0]
        neg_freq = np.histogram(scores[~y], bins)[0]
        pos_freq = pos_freq / pos_freq.sum()
        neg_freq = neg_freq / neg_freq.sum()

        score_hist_pos = {
            'bins': bins, 'pos_freq': pos_freq, 'neg_freq': neg_freq}

        lnbnn_xy = results['lnbnn_xy']
        scores = lnbnn_xy['score_lnbnn_1vM'].values
        y = lnbnn_xy[POSTV].values

        # Get 95% of the data at least
        maxbin = scores[scores.argsort()][-max(1, int(len(scores) * .05))]
        bins = np.linspace(0, max(maxbin, 10), 100)
        pos_freq = np.histogram(scores[y], bins)[0]
        neg_freq = np.histogram(scores[~y], bins)[0]
        pos_freq = pos_freq / pos_freq.sum()
        neg_freq = neg_freq / neg_freq.sum()
        score_hist_lnbnn = {
            'bins': bins, 'pos_freq': pos_freq, 'neg_freq': neg_freq}

        fig1 = self._draw_score_hist(score_hist_pos, 'positive probability', 1)
        fig2 = self._draw_score_hist(score_hist_lnbnn, 'LNBNN score', 2)

        fname = 'score_hist_pos_{}.png'.format(data_key)
        vt.imwrite(join(str(self.dpath), fname),
                   pt.render_figure_to_image(fig1, dpi=DPI))

        fname = 'score_hist_lnbnn.png'
        vt.imwrite(join(str(self.dpath), fname),
                   pt.render_figure_to_image(fig2, dpi=DPI))

    def draw_mcc_thresh(self, task_key):
        """
        python -m ibeis Chap4.draw mcc_thresh GZ_Master1 match_state
        python -m ibeis Chap4.draw mcc_thresh PZ_Master1 match_state

        python -m ibeis Chap4.draw mcc_thresh GZ_Master1 photobomb_state
        python -m ibeis Chap4.draw mcc_thresh PZ_Master1 photobomb_state

        """
        mpl.rcParams.update(TMP_RC)

        results = self.ensure_results('all')
        data_key = results['data_key']
        clf_key = results['clf_key']

        task_combo_res = results['task_combo_res']

        code_to_nice = self.task_nice_lookup[task_key]

        if task_key == 'photobomb_state':
            classes = ['pb']
        elif task_key == 'match_state':
            classes = [POSTV, NEGTV, INCMP]

        res = task_combo_res[task_key][clf_key][data_key]

        roc_curves = []

        for class_name in classes:
            c1 = res.confusions(class_name)
            if len(c1.thresholds) <= 2:
                continue
            class_nice = code_to_nice[class_name]
            idx = c1.mcc.argmax()
            t = c1.thresholds[idx]
            mcc = c1.mcc[idx]
            roc_curves += [
                {'label': class_nice + ', t={:.2f}, mcc={:.2f}'.format(t, mcc),
                 'thresh': c1.thresholds, 'mcc': c1.mcc},
            ]

        fig = pt.figure(fnum=1)  # NOQA
        ax = pt.gca()
        for data in roc_curves:
            ax.plot(data['thresh'], data['mcc'], label='%s' % (data['label']))
        ax.set_xlabel('threshold')
        ax.set_ylabel('MCC')
        # ax.set_title('%s ROC for %s' % (target_class.title(), self.species))
        ax.legend()
        pt.adjust_subplots(top=.8, bottom=.2, left=.12, right=.9)
        fig.set_size_inches([W, H])

        fname = 'mcc_thresh_{}.png'.format(task_key)
        fig_fpath = join(str(self.dpath), fname)
        vt.imwrite(fig_fpath, pt.render_figure_to_image(fig, dpi=DPI))
        if ut.get_argflag('--diskshow'):
            ut.startfile(fig_fpath)

    def draw_roc(self, task_key):
        """
        python -m ibeis Chap4.draw roc GZ_Master1 photobomb_state
        python -m ibeis Chap4.draw roc GZ_Master1 match_state
        """
        mpl.rcParams.update(TMP_RC)

        results = self.ensure_results('all')
        data_key = results['data_key']
        clf_key = results['clf_key']

        task_combo_res = results['task_combo_res']
        lnbnn_xy = results['lnbnn_xy']

        if task_key == 'match_state':
            scores = lnbnn_xy['score_lnbnn_1vM'].values
            y = lnbnn_xy[POSTV].values
            # task_key = 'match_state'
            target_class = POSTV
            res = task_combo_res[task_key][clf_key][data_key]
            c2 = vt.ConfusionMetrics.from_scores_and_labels(scores, y)
            c3 = res.confusions(target_class)
            roc_curves = [
                {'label': 'LNBNN', 'fpr': c2.fpr, 'tpr': c2.tpr, 'auc': c2.auc},
                {'label': 'learned', 'fpr': c3.fpr, 'tpr': c3.tpr, 'auc': c3.auc},
            ]

            at_metric = 'tpr'
            for at_value in [.25, .5, .75]:
                info = ut.odict()
                for want_metric in ['fpr', 'n_false_pos', 'n_true_pos']:
                    key = '{}_@_{}={:.2f}'.format(want_metric, at_metric, at_value)
                    info[key] = c3.get_metric_at_metric(want_metric, at_metric, at_value)
                print(ut.repr4(info, align=True, precision=8))
        else:
            target_class = 'pb'
            res = task_combo_res[task_key][clf_key][data_key]
            c1 = res.confusions(target_class)
            roc_curves = [
                {'label': 'learned', 'fpr': c1.fpr, 'tpr': c1.tpr, 'auc': c1.auc},
            ]

        fig = pt.figure(fnum=1)  # NOQA
        ax = pt.gca()
        for data in roc_curves:
            ax.plot(data['fpr'], data['tpr'],
                    label='%s AUC=%.2f' % (data['label'], data['auc']))
        ax.set_xlabel('false positive rate')
        ax.set_ylabel('true positive rate')
        # ax.set_title('%s ROC for %s' % (target_class.title(), self.species))
        ax.legend()
        pt.adjust_subplots(top=.8, bottom=.2, left=.12, right=.9)
        fig.set_size_inches([W, H])

        fname = 'roc_{}.png'.format(task_key)
        fig_fpath = join(str(self.dpath), fname)
        vt.imwrite(fig_fpath, pt.render_figure_to_image(fig, dpi=DPI))

    def draw_wordcloud(self, task_key):
        import plottool as pt
        results = self.ensure_results('all')
        importances = ut.map_keys(feat_alias, results['importance'][task_key])

        fig = pt.figure(fnum=1)
        pt.wordcloud(importances, ax=fig.axes[0])

        fname = 'wc_{}.png'.format(task_key)
        fig_fpath = join(str(self.dpath), fname)
        vt.imwrite(fig_fpath, pt.render_figure_to_image(fig, dpi=DPI))

    @classmethod
    def draw_tagged_pair(Chap4):
        import ibeis
        # ibs = ibeis.opendb(defaultdb='GZ_Master1')
        ibs = ibeis.opendb(defaultdb='PZ_Master1')

        query_tag = 'leftrightface'

        rowids = ibs._get_all_annotmatch_rowids()
        texts = ['' if t is None else t for t in ibs.get_annotmatch_tag_text(rowids)]
        tags = [[] if t is None else t.split(';') for t in texts]
        print(ut.repr4(ut.dict_hist(ut.flatten(tags))))

        flags = [query_tag in t.lower() for t in texts]
        filtered_rowids = ut.compress(rowids, flags)
        edges = ibs.get_annotmatch_aids(filtered_rowids)

        # The facematch leftright side example
        # edge = (5161, 5245)

        edge = edges[0]
        # for edge in ut.InteractiveIter(edges):
        infr = ibeis.AnnotInference(ibs=ibs, aids=edge, verbose=10)
        infr.reset_feedback('annotmatch', apply=True)
        match = infr._exec_pairwise_match([edge])[0]

        if False:
            # Fix the example tags
            infr.add_feedback(
                edge, 'match', tags=['facematch', 'leftrightface'],
                user_id='qt-hack', confidence='pretty_sure')
            infr.write_ibeis_staging_feedback()
            infr.write_ibeis_annotmatch_feedback()
            pass

        # THE DEPCACHE IS BROKEN FOR ANNOTMATCH APPARENTLY! >:(
        # Redo matches
        feat_keys = ['vecs', 'kpts', '_feats', 'flann']
        match.annot1._mutable = True
        match.annot2._mutable = True
        for key in feat_keys:
            if key in match.annot1:
                del match.annot1[key]
            if key in match.annot2:
                del match.annot2[key]
        match.apply_all({})

        fig = pt.figure(fnum=1, clf=True)
        ax = pt.gca()

        mpl.rcParams.update(TMP_RC)
        match.show(ax, vert=False,
                   heatmask=True,
                   show_lines=False,
                   show_ell=False,
                   show_ori=False,
                   show_eig=False,
                   # ell_alpha=.3,
                   modifysize=True)
        # ax.set_xlabel(xlabel)

        self = Chap4()

        fname = 'custom_match_{}_{}_{}'.format(query_tag, *edge)
        dpath = pathlib.Path(ut.truepath(self.base_dpath))
        fpath = join(str(dpath), fname + '.jpg')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))

    def custom_single_hard_case(self):
        """
        Example:
            >>> from ibeis.scripts.thesis import *
            >>> defaultdb = 'PZ_PB_RF_TRAIN'
            >>> #defaultdb = 'GZ_Master1'
            >>> defaultdb = 'PZ_MTEST'
            >>> self = Chap4.collect(defaultdb)
            >>> self.dbname = 'PZ_PB_RF_TRAIN'
        """
        task_key = 'match_state'
        edge = (383, 503)
        for _case in self.hard_cases[task_key]:
            if _case['edge'] == edge:
                case = _case
                break

        import ibeis
        ibs = ibeis.opendb(self.dbname)

        from ibeis import core_annots
        config = {
            'augment_orientation': True,
            'ratio_thresh': .8,
        }
        config['checks'] = 80
        config['sver_xy_thresh'] = .02
        config['sver_ori_thresh'] = 3
        config['Knorm'] = 3
        config['symmetric'] = True
        config = ut.hashdict(config)

        aid1, aid2 = case['edge']
        real_name = case['real']
        pred_name = case['pred']
        match = case['match']
        code_to_nice = self.task_nice_lookup[task_key]
        real_nice, pred_nice = ut.take(code_to_nice,
                                       [real_name, pred_name])
        fname = 'fail_{}_{}_{}_{}'.format(real_nice, pred_nice, aid1, aid2)
        # Draw case
        probs = case['probs'].to_dict()
        order = list(code_to_nice.values())
        order = ut.setintersect(order, probs.keys())
        probs = ut.map_dict_keys(code_to_nice, probs)
        probstr = ut.repr2(probs, precision=2, strkeys=True, nobr=True,
                           key_order=order)
        xlabel = 'real={}, pred={},\n{}'.format(real_nice, pred_nice,
                                                probstr)

        match_list = ibs.depc.get('pairwise_match', ([aid1], [aid2]),
                                       'match', config=config)
        match = match_list[0]
        configured_lazy_annots = core_annots.make_configured_annots(
            ibs, [aid1], [aid2], config, config, preload=True)
        match.annot1 = configured_lazy_annots[config][aid1]
        match.annot2 = configured_lazy_annots[config][aid2]
        match.config = config

        fig = pt.figure(fnum=1, clf=True)
        ax = pt.gca()

        mpl.rcParams.update(TMP_RC)
        match.show(ax, vert=False,
                   heatmask=True,
                   show_lines=False,
                   show_ell=False,
                   show_ori=False,
                   show_eig=False,
                   # ell_alpha=.3,
                   modifysize=True)
        ax.set_xlabel(xlabel)

        subdir = 'cases_{}'.format(task_key)
        dpath = join(str(self.dpath), subdir)
        fpath = join(str(dpath), fname + '_custom.jpg')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))


@ut.reloadable_class
class Chap3Commands(object):
    @classmethod
    def vd(Chap3):
        """
        CommandLine:
            python -m ibeis Chap3.vd
        """
        ut.vd(Chap3.base_dpath)

    @classmethod
    def run_all(Chap3):
        """
        CommandLine:
            python -m ibeis Chap3.run_all
        """
        agg_dbnames = ['PZ_Master1', 'GZ_Master1', 'GIRM_Master1',
                       'humpbacks_fb']
        agg_dbnames = agg_dbnames[::-1]

        for dbname in agg_dbnames:
            self = Chap3(dbname)
            self.measure_all()
            self.draw_time_distri()

        Chap3.agg_dbstats()
        Chap3.draw_agg_baseline()

    def _setup(self):
        self._precollect()

    def measure_all(self):
        """
        Example:
            from ibeis.scripts.thesis import *
            self = Chap3('PZ_Master1')
            self.measure_all()
            self = Chap3('GZ_Master1')
            self.measure_all()
            self = Chap3('GIRM_Master1')
            self.measure_all()
        """
        if self.ibs is None:
            self._precollect()
        self.measure_baseline()
        if self.dbname in {'PZ_Master1', 'GZ_Master1'}:
            self.measure_foregroundness()
            self.measure_smk()
            self.measure_nsum()
            # self.measure_dbsize()
            self.measure_kexpt()
            self.measure_invar()

    @classmethod
    def measure(Chap3, expt_name, dbnames):
        """
        CommandLine:
            python -m ibeis Chap3.measure all --dbs=GZ_Master1
            python -m ibeis Chap3.measure all --dbs=PZ_Master1

            python -m ibeis Chap3.measure nsum --dbs=GZ_Master1,PZ_Master1
            python -m ibeis Chap3.measure foregroundness --dbs=GZ_Master1,PZ_Master1

        Example:
            >>> # Script
            >>> from ibeis.scripts.thesis import *  # NOQA
            >>> expt_name = ut.get_argval('--expt', type_=str, pos=1)
            >>> dbnames = ut.get_argval(('--dbs', '--db'), type_=list, default=[])
            >>> Chap3.measure(expt_name, dbnames)
        """
        for dbname in dbnames:
            self = Chap3(dbname)
            if self.ibs is None:
                self._precollect()
            if expt_name == 'all':
                self.measure_all()
            else:
                getattr(self, 'measure_' + expt_name)()

    @classmethod
    def draw(Chap3, expt_name, dbnames):
        """
        CommandLine:
            python -m ibeis Chap3.draw nsum --dbs=GZ_Master1,PZ_Master1
            python -m ibeis Chap3.draw foregroundness --dbs=GZ_Master1,PZ_Master1 --diskshow
            python -m ibeis Chap3.draw kexpt --dbs=GZ_Master1 --diskshow

        Example:
            >>> # Script
            >>> from ibeis.scripts.thesis import *  # NOQA
            >>> expt_name = ut.get_argval('--expt', type_=str, pos=1)
            >>> dbnames = ut.get_argval(('--dbs', '--db'), type_=list, default=[])
            >>> Chap3.draw(expt_name, dbnames)
        """
        print('dbnames = %r' % (dbnames,))
        print('expt_name = %r' % (expt_name,))
        super(Chap3.__class__, Chap3).draw(expt_name, dbnames)
        # for dbname in dbnames:
        #     self = Chap3(dbname)
        #     if expt_name == 'all':
        #         self.draw_all()
        #     else:
        #         draw_func = getattr(self, 'draw_' + expt_name, None)
        #         if draw_func is None:
        #             draw_func = getattr(self, 'write_' + expt_name, None)
        #         if draw_func is None:
        #             raise ValueError('Cannot find a way to draw ' + expt_name)
        #         fpath = draw_func()
        #         if ut.get_argflag('--diskshow'):
        #             if isinstance(fpath, six.text_type):
        #                 ut.startfile(fpath)
        #             else:
        #                 fpath_list = fpath
        #                 for fpath in fpath_list:
        #                     ut.startfile(fpath)


@ut.reloadable_class
class Chap3Agg(object):
    @classmethod
    def agg_dbstats(Chap3):
        """
        CommandLine:
            python -m ibeis Chap3.agg_dbstats
            python -m ibeis Chap3.measure_dbstats

        Example:
            >>> # DISABLE_DOCTEST
            >>> from ibeis.scripts.thesis import *  # NOQA
            >>> result = Chap3.agg_dbstats()
            >>> print(result)
        """
        agg_dbnames = ['PZ_Master1', 'GZ_Master1', 'GIRM_Master1', 'humpbacks_fb']
        infos = ut.ddict(list)
        for dbname in agg_dbnames:
            self = Chap3(dbname)
            info = self.ensure_results('dbstats')
            infos['enc'].append(info['enc'])
            infos['qual'].append(info['qual'])
            infos['view'].append(info['view'])
            # labels.append(self.species_nice.capitalize())

        df = pd.DataFrame(infos['enc'])
        # df = df.reindex_axis(ut.partial_order(df.columns, ['species_nice']), axis=1)
        df = df.rename(columns={'species_nice': 'Database'})
        text = df.to_latex(index=False, na_repr='nan').replace('±', '\pm')
        text = text.replace(r'n\_singleton\_names', r'\thead{\#names\\(singleton)}')
        text = text.replace(r'n\_resighted\_names', r'\thead{\#names\\(resighted)}')
        text = text.replace(r'n\_encounter\_per\_resighted\_name', r'\thead{\#encounter per\\name (resighted)}')
        text = text.replace(r'n\_annots\_per\_encounter', r'\thead{\#annots per\\encounter}')
        text = text.replace(r'n\_annots', r'\thead{\#annots}')
        enc_text = text.replace('lrrllr', 'lrrrrr')
        # ut.render_latex_text(text, preamb_extra='\\usepackage{makecell}')

        df = pd.DataFrame(infos['qual'])
        df = df.rename(columns={'species_nice': 'Database'})
        df = df.reindex_axis(ut.partial_order(
            df.columns, ['Database', 'excellent', 'good', 'ok', 'poor', 'None']), axis=1)
        qual_text = df.to_latex(index=False, na_repr='nan')

        df = pd.DataFrame(infos['view'])
        df = df.rename(columns={
            'species_nice': 'Database',
            'back': 'B', 'left': 'L', 'right': 'R', 'front': 'F',
            'backleft': 'BL', 'backright': 'BR', 'frontright': 'FR',
            'frontleft': 'FL',
        })
        order = ut.partial_order(
            df.columns, ['Database', 'BL', 'L', 'FL', 'F', 'FR', 'R', 'BR',
                         'B', 'None'])
        df = df.reindex_axis(order, axis=1)
        df = df.set_index('Database')
        df[pd.isnull(df)] = 0
        df = df.astype(np.int).reset_index()
        view_text = df.to_latex(index=False, na_repr='nan')

        ut.write_to(join(Chap3.base_dpath, 'agg-enc.tex'), enc_text)
        ut.write_to(join(Chap3.base_dpath, 'agg-view.tex'), view_text)
        ut.write_to(join(Chap3.base_dpath, 'agg-qual.tex'), qual_text)

    @classmethod
    def draw_agg_baseline(Chap3):
        """
        CommandLine:
            python -m ibeis Chap3.draw_agg_baseline --diskshow

        Example:
            >>> # SCRIPT
            >>> from ibeis.scripts.thesis import *  # NOQA
            >>> Chap3.draw_agg_baseline()
        """
        agg_dbnames = ['GZ_Master1', 'PZ_Master1', 'GIRM_Master1', 'humpbacks_fb']
        cdfs = []
        labels = []
        for dbname in agg_dbnames:
            self = Chap3(dbname)
            results = self.ensure_results('baseline')
            cdf, config = results[0]
            dsize = config['dsize']
            qsize = config['t_n_names']
            baseline_cdf = results[0][0]
            cdfs.append(baseline_cdf)
            labels.append('{},qsize={},dsize={}'.format(
                self.species_nice, qsize, dsize))
            # labels.append(self.species_nice.capitalize())

        mpl.rcParams.update(TMP_RC)
        fig = plot_cmcs(cdfs, labels, fnum=1, ymin=.5)
        fig.set_size_inches([W, H * 1.5])
        fpath = join(Chap3.base_dpath, 'agg-baseline.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        if ut.get_argflag('--diskshow'):
            ut.startfile(fpath)


@ut.reloadable_class
class Chap3Measures(object):
    def measure_baseline(self):
        """
            >>> from ibeis.scripts.thesis import *
            >>> self = Chap3('GZ_Master1')
            >>> self._precollect()
        """
        ibs = self.ibs
        qaids, daids_list, info_list = Sampler._varied_inputs(
            self.ibs, self.aids_pool,
            denc_per_name=[1], extra_dbsize_fracs=[1])
        cfgdict = {}
        daids = daids_list[0]
        info = info_list[0]
        cdf = _ranking_cdf(ibs, qaids, daids, cfgdict)
        results = [(cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict}))]

        expt_name = 'baseline'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)

    def measure_foregroundness_intra(self):
        ibs = self.ibs
        samples = Sampler._intra_enc(ibs, self.aids_pool)
        # qaids, daids_list, info_list = sample.expand()

        results = []
        for sample in samples:
            qaids = sample.qaids
            daids = sample.daids
            info = {'qsize': len(qaids), 'dsize': len(daids)}
            grid = ut.all_dict_combinations(
                {'featweight_enabled': [False, True]}
            )
            for cfgdict in grid:
                hist = _ranking_hist(ibs, qaids, daids, cfgdict)
                info = ut.update_dict(info.copy(), {'pcfg': cfgdict})
                results.append((hist, info))

        expt_name = 'foregroundness_intra'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)

    def draw_foregroundness_intra(self):
        """
        python -m ibeis Chap3.measure foregroundness_intra --dbs=GZ_Master1,PZ_Master1
        python -m ibeis Chap3.draw foregroundness_intra --dbs=GZ_Master1,PZ_Master1 --diskshow
        """
        expt_name = ut.get_stack_frame().f_code.co_name.replace('draw_', '')
        expt_name = 'foregroundness_intra'

        mpl.rcParams.update(TMP_RC)
        results = self.ensure_results(expt_name)
        hists, infos = list(zip(*results))
        pcfgs = ut.take_column(infos, 'pcfg')
        df = pd.DataFrame.from_records(infos)
        df['hists'] = hists
        df['fg_on'] = ut.take_column(pcfgs, 'featweight_enabled')

        cdfs = []
        labels = []

        for fg, group in df.groupby(('fg_on')):
            labels.append('fg=T' if fg else 'fg=F')
            hists = vt.pad_vstack(group['hists'], fill_value=0)
            hist = hists.sum(axis=0)
            cdf = (np.cumsum(hist) / sum(hist))
            cdfs.append(cdf)
            qsize = str(group['qsize'].sum())
            dsize = '{:.1f}±{:.1f}'.format(group['dsize'].mean(), group['dsize'].std())

        fig = plot_cmcs(cdfs, labels, ymin=.5)
        fig.set_size_inches([W, H * .6])
        nonvaried_text = 'qsize={:s}, dsize={:s}'.format(qsize, dsize)
        pt.relative_text('lowerleft', nonvaried_text, ax=pt.gca())
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath

    def measure_foregroundness(self):
        ibs = self.ibs
        qaids, daids_list, info_list = Sampler._varied_inputs(
            self.ibs, self.aids_pool,
            denc_per_name=[1], extra_dbsize_fracs=[1],
            method='same_occur'
            # method='same_enc'
        )
        daids = daids_list[0]
        info = info_list[0]

        results = []
        cfgdict1 = {'fg_on': False}
        cdf = _ranking_cdf(ibs, qaids, daids, cfgdict1)
        results.append((cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict1})))

        cfgdict2 = {'fg_on': True}
        cdf = _ranking_cdf(ibs, qaids, daids, cfgdict2)
        results.append((cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict2})))

        expt_name = 'foregroundness'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)

    def measure_invar(self):
        ibs = self.ibs
        qaids, daids_list, info_list = Sampler._varied_inputs(
            self.ibs, self.aids_pool,
            denc_per_name=[1], extra_dbsize_fracs=[1])
        daids = daids_list[0]
        info = info_list[0]

        cfgdict_list = [
            {'affine_invariance':  True, 'rotation_invariance': False, 'query_rotation_heuristic': False},
            # {'affine_invariance':  True, 'rotation_invariance':  True, 'query_rotation_heuristic': False},
            # {'affine_invariance': False, 'rotation_invariance':  True, 'query_rotation_heuristic': False},
            {'affine_invariance': False, 'rotation_invariance': False, 'query_rotation_heuristic': False},
            {'affine_invariance':  True, 'rotation_invariance': False, 'query_rotation_heuristic':  True},
            {'affine_invariance': False, 'rotation_invariance': False, 'query_rotation_heuristic':  True},
        ]
        results = []
        for cfgdict in cfgdict_list:
            cdf = _ranking_cdf(ibs, qaids, daids, cfgdict)
            results.append((cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict})))

        expt_name = 'invar'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)

    def measure_smk(self):
        """
        python -m ibeis Chap3.measure smk --dbs=GZ_Master1,PZ_Master1
        python -m ibeis Chap3.draw smk --dbs=GZ_Master1,PZ_Master1 --diskshow
        """
        from ibeis.algo.smk.smk_pipeline import SMKRequest
        # ibs = ibeis.opendb('PZ_MTEST')
        ibs = self.ibs
        qaids, daids_list, info_list = Sampler._varied_inputs(
            self.ibs, self.aids_pool,
            denc_per_name=[1], extra_dbsize_fracs=[1])
        daids = daids_list[0]
        info = info_list[0]
        results = []

        # SMK pipeline
        config = {'nAssign': 1, 'num_words': 8000, 'sv_on': True}
        qreq_ = SMKRequest(ibs, qaids, daids, config)
        qreq_.ensure_data()
        cm_list = qreq_.execute()
        cm_list = [cm.extend_results(qreq_) for cm in cm_list]
        name_ranks = [cm.get_name_ranks([cm.qnid])[0] for cm in cm_list]
        bins = np.arange(len(qreq_.dnids))
        hist = np.histogram(name_ranks, bins=bins)[0]
        cdf = (np.cumsum(hist) / sum(hist))
        results.append((cdf, ut.update_dict(info.copy(), {'pcfg': config})))

        # LNBNN pipeline
        cfgdict = {}
        cdf = _ranking_cdf(ibs, qaids, daids, cfgdict)
        results.append((cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict})))

        expt_name = 'smk'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)

    def measure_nsum(self):
        """
        python -m ibeis Chap3.measure nsum --dbs=GZ_Master1,PZ_Master1
        python -m ibeis Chap3.draw nsum --dbs=GZ_Master1,PZ_Master1 --diskshow

        from ibeis.scripts.thesis import *
        self = Chap3('GZ_Master1')
        self = Chap3('PZ_Master1')
        self = Chap3('PZ_MTEST')
        self._precollect()
        """
        ibs = self.ibs
        qaids, daids_list, info_list = Sampler._varied_inputs(
            self.ibs, self.aids_pool,
            denc_per_name=[1, 2, 3], extra_dbsize_fracs=[1])

        base = {'query_rotation_heuristic': True}
        cfgdict1 = ut.dict_union(base, {'score_method': 'nsum', 'prescore_method': 'nsum'})
        cfgdict2 = ut.dict_union(base, {'score_method': 'csum', 'prescore_method': 'csum'})
        results = []
        for count, (daids, info) in enumerate(zip(daids_list, info_list), start=1):
            cdf1 = _ranking_cdf(ibs, qaids, daids, cfgdict1)
            results.append((cdf1, ut.update_dict(info.copy(), {'pcfg': cfgdict1})))
            cdf2 = _ranking_cdf(ibs, qaids, daids, cfgdict2)
            results.append((cdf2, ut.update_dict(info.copy(), {'pcfg': cfgdict2})))

        if False:
            self._precollect()
            ibs = self.ibs
            qaids, daids_list, info_list = Sampler._varied_inputs(
                self.ibs, self.aids_pool,
                denc_per_name=[1, 2, 3], extra_dbsize_fracs=[1])
            # Check dpername issue
            base = {'query_rotation_heuristic': False, 'K': 1, 'sv_on': True}
            cfgdict1 = ut.dict_union(base, {'score_method': 'nsum', 'prescore_method': 'nsum'})
            cfgdict2 = ut.dict_union(base, {'score_method': 'csum', 'prescore_method': 'csum'})

            qaids = [2491]

            info = {}
            daids = daids_list[0]
            a = ibs.annots(daids)
            daids = a.compress(ut.flag_unique_items(a.nids)).aids

            while True:
                qreq1_ = ibs.new_query_request(qaids, daids, cfgdict=cfgdict1)
                qreq2_ = ibs.new_query_request(qaids, daids, cfgdict=cfgdict2)
                cm_list1 = qreq1_.execute(use_cache=False)
                cm_list2 = qreq2_.execute(use_cache=False)
                cm1 = cm_list1[0]
                cm2 = cm_list2[0]
                assert (cm1 == cm2)

            # cm_list1 = [cm.extend_results(qreq1_) for cm in cm_list1]
            # cm_list2 = [cm.extend_results(qreq2_) for cm in cm_list2]

            # cm_list1 = [cm.compress_results() for cm in cm_list1]
            # cm_list2 = [cm.compress_results() for cm in cm_list2]

            name_ranks1 = [cm.get_name_ranks([cm.qnid])[0] for cm in cm_list1]
            name_ranks2 = [cm.get_name_ranks([cm.qnid])[0] for cm in cm_list2]

            idxs = np.where(np.array(name_ranks1) != np.array(name_ranks2))[0]
            print('idxs = %r' % (idxs,))
            print('ranks1 = {}'.format(ut.take(name_ranks1, idxs)))
            print('ranks2 = {}'.format(ut.take(name_ranks2, idxs)))
            if len(idxs) > 0:
                cm1 = cm_list1[idxs[0]]  # NOQA
                cm2 = cm_list2[idxs[0]]  # NOQA

        expt_name = 'nsum'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)

    def measure_dbsize(self):
        ibs = self.ibs
        qaids, daids_list, info_list = Sampler._varied_inputs(
            self.ibs, self.aids_pool,
            denc_per_name=[1, 2], extra_dbsize_fracs=[0, 1.0])
        cfgdict = {
            'query_rotation_heuristic': True,
        }
        results = []
        for daids, info in zip(daids_list, info_list):
            info = info.copy()
            cdf = _ranking_cdf(ibs, qaids, daids, cfgdict)
            results.append((cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict})))

        expt_name = 'dsize'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)
        cdfs, infos = zip(*results)

    def measure_kexpt(self):
        ibs = self.ibs
        qaids, daids_list, info_list = Sampler._varied_inputs(
            self.ibs, self.aids_pool,
            denc_per_name=[1, 2], extra_dbsize_fracs=[0, 1.0])
        cfg_grid = {
            'query_rotation_heuristic': True,
            'K': [1, 2, 4, 6],
        }
        results = []
        for cfgdict in ut.all_dict_combinations(cfg_grid):
            for daids, info in zip(daids_list, info_list):
                cdf = _ranking_cdf(ibs, qaids, daids, cfgdict)
                results.append((cdf, ut.update_dict(info.copy(), {'pcfg': cfgdict})))

        expt_name = 'kexpt'
        self.expt_results[expt_name] = results
        ut.save_data(join(self.dpath, expt_name + '.pkl'), results)

    def measure_dbstats(self):
        if self.ibs is None:
            self._precollect()

        # self.ibs.print_annot_stats(self.aids_pool)
        annots = self.ibs.annots(self.aids_pool)

        encounters = annots.group(annots.encounter_text)[1]
        nids = ut.take_column(self.ibs._annot_groups(encounters).nids, 0)
        nid_to_enc = ut.group_items(encounters, nids)

        single_encs = {nid: e for nid, e in nid_to_enc.items() if len(e) == 1}
        multi_encs = {nid: e for nid, e in nid_to_enc.items() if len(e) > 1}
        multi_aids = ut.flatten(ut.flatten(multi_encs.values()))

        enc_deltas = []
        for encs_ in nid_to_enc.values():
            a = encs_[0]
            times = a.image_unixtimes_asfloat
            delta = times.max() - times.min()
            enc_deltas.append(delta)
        max_enc_timedelta = max(enc_deltas)
        print('max enc timedelta = %r' % (
            ut.get_unix_timedelta_str(max_enc_timedelta)))

        multi_stats = self.ibs.get_annot_stats_dict(multi_aids)
        multi_stats['enc_per_name']

        enc_info = ut.odict()
        enc_info['species_nice'] = self.species_nice
        enc_info['n_singleton_names'] = len(single_encs)
        enc_info['n_resighted_names'] = len(multi_encs)
        enc_info['n_encounter_per_resighted_name'] = '{:.1f}±{:.1f}'.format(
            *ut.take(multi_stats['enc_per_name'], ['mean', 'std']))
        n_annots_per_enc = ut.lmap(len, encounters)
        enc_info['n_annots_per_encounter'] = '{:.1f}±{:.1f}'.format(
            np.mean(n_annots_per_enc), np.std(n_annots_per_enc))
        enc_info['n_annots'] = sum(n_annots_per_enc)

        # qual_info = ut.odict()
        qual_info = ut.dict_hist(annots.quality_texts)
        qual_info['None'] = qual_info.pop('UNKNOWN', 0)
        qual_info['None'] += qual_info.pop(None, 0)
        qual_info['species_nice'] = self.species_nice

        view_info = ut.dict_hist(annots.yaw_texts)
        view_info['None'] = view_info.pop('UNKNOWN', 0)
        view_info['None'] += view_info.pop(None, 0)
        view_info['species_nice'] = self.species_nice

        info = {
            'enc': enc_info,
            'qual': qual_info,
            'view': view_info,
        }

        expt_name = ut.get_stack_frame().f_code.co_name.replace('measure_', '')
        expt_name = 'dbstats'
        self.expt_results[expt_name] = info
        ut.save_data(join(self.dpath, expt_name + '.pkl'), info)
        return info


@ut.reloadable_class
class Chap3Draw(object):
    def draw_baseline(self):
        mpl.rcParams.update(TMP_RC)
        expt_name = ut.get_stack_frame().f_code.co_name.replace('draw_', '')
        results = self.ensure_results(expt_name)
        cdfs, infos = list(zip(*results))
        baseline_cdf = cdfs[0]
        fig = plot_cmcs([baseline_cdf], ['baseline'], fnum=1)
        fig.set_size_inches([W, H * .6])
        qsizes = ut.take_column(infos, 'qsize')
        dsizes = ut.take_column(infos, 'dsize')
        assert ut.allsame(qsizes) and ut.allsame(dsizes)
        nonvaried_text = 'qsize={}, dsize={}'.format(qsizes[0], dsizes[0])
        pt.relative_text('lowerleft', nonvaried_text, ax=pt.gca())
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath

    def draw_smk(self):
        """
        ibeis Chap3.measure smk --dbs=GZ_Master1,PZ_Master1
        ibeis Chap3.draw smk --dbs=GZ_Master1,PZ_Master1
        """
        mpl.rcParams.update(TMP_RC)
        expt_name = ut.get_stack_frame().f_code.co_name.replace('draw_', '')
        results = self.ensure_results(expt_name)
        cdfs, infos = list(zip(*results))
        labels = ['smk', 'baseline']
        fig = plot_cmcs(cdfs, labels, fnum=1, ymin=.5)
        fig.set_size_inches([W, H * .6])
        qsizes = ut.take_column(infos, 'qsize')
        dsizes = ut.take_column(infos, 'dsize')
        assert ut.allsame(qsizes) and ut.allsame(dsizes)
        nonvaried_text = 'qsize={}, dsize={}'.format(qsizes[0], dsizes[0])
        pt.relative_text('lowerleft', nonvaried_text, ax=pt.gca())
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath

    def draw_foregroundness(self):
        """
        ibeis Chap3.measure foregroundness --dbs=GZ_Master1,PZ_Master1
        ibeis Chap3.draw foregroundness --dbs=GZ_Master1,PZ_Master1
        """
        mpl.rcParams.update(TMP_RC)
        expt_name = ut.get_stack_frame().f_code.co_name.replace('draw_', '')
        results = self.ensure_results(expt_name)
        cdfs, infos = list(zip(*results))
        labels = ['fg=F', 'fg=T']
        fig = plot_cmcs(cdfs, labels, fnum=1, ymin=.5)
        fig.set_size_inches([W, H * .6])
        qsizes = ut.take_column(infos, 'qsize')
        dsizes = ut.take_column(infos, 'dsize')
        assert ut.allsame(qsizes) and ut.allsame(dsizes)
        nonvaried_text = 'qsize={}, dsize={}'.format(qsizes[0], dsizes[0])
        pt.relative_text('lowerleft', nonvaried_text, ax=pt.gca())
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath

    def draw_invar(self):
        """
        ibeis Chap3.measure invar --dbs=GZ_Master1,PZ_Master1
        ibeis Chap3.draw invar --dbs=GZ_Master1,PZ_Master1
        """
        mpl.rcParams.update(TMP_RC)
        expt_name = ut.get_stack_frame().f_code.co_name.replace('draw_', '')
        results = self.ensure_results(expt_name)
        ALIAS_KEYS = ut.invert_dict({
            'RI': 'rotation_invariance',
            'AI': 'affine_invariance',
            'QRH': 'query_rotation_heuristic', })
        results = [(c, i) for c, i in results
                   if not i['pcfg'].get('rotation_invariance', False)]
        cdfs, infos = list(zip(*results))
        pcfgs = ut.take_column(infos, 'pcfg')

        for p in pcfgs:
            del p['rotation_invariance']

        labels = [ut.get_cfg_lbl(ut.map_keys(ALIAS_KEYS, pcfg))[1:] for pcfg in pcfgs]
        labels = ut.lmap(label_alias, labels)
        fig = plot_cmcs(cdfs, labels, fnum=1, ymin=.5)
        fig.set_size_inches([W, H * .6])
        qsizes = ut.take_column(infos, 'qsize')
        dsizes = ut.take_column(infos, 'dsize')
        assert ut.allsame(qsizes) and ut.allsame(dsizes)
        nonvaried_text = 'qsize={}, dsize={}'.format(qsizes[0], dsizes[0])
        pt.relative_text('lowerleft', nonvaried_text, ax=pt.gca())
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath

    def draw_nsum(self):
        """
        ibeis Chap3.measure nsum --dbs=GZ_Master1,PZ_Master1
        ibeis Chap3.draw nsum --dbs=GZ_Master1,PZ_Master1
        """
        mpl.rcParams.update(TMP_RC)
        expt_name = ut.get_stack_frame().f_code.co_name.replace('draw_', '')
        expt_name = 'nsum'
        results = self.ensure_results(expt_name)
        cdfs, infos = list(zip(*results))
        # pcfgs = ut.take_column(infos, 'pcfg')
        alias = {
            'nsum': 'fmech',
            'csum': 'amech',
        }
        labels = [alias[x['pcfg']['score_method']] + ',dpername={}'.format(x['t_dpername']) for x in infos]
        fig = plot_cmcs(cdfs, labels, fnum=1, ymin=.5)
        qsizes = ut.take_column(infos, 'qsize')
        dsizes = ut.take_column(infos, 'dsize')
        assert ut.allsame(qsizes) and ut.allsame(dsizes)
        nonvaried_text = 'qsize={}, dsize={}'.format(qsizes[0], dsizes[0])
        pt.relative_text('lowerleft', nonvaried_text, ax=pt.gca())
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath

    def draw_kexpt(self):
        """
        ibeis Chap3.measure kexpt --dbs=GZ_Master1,PZ_Master1
        ibeis Chap3.draw kexpt --dbs=GZ_Master1,PZ_Master1 --diskshow
        """
        mpl.rcParams.update(TMP_RC)
        expt_name = ut.get_stack_frame().f_code.co_name.replace('draw_', '')
        results = self.ensure_results(expt_name)
        # results = self.expt_results[expt_name]
        cdfs, infos = list(zip(*results))
        pcfgs = ut.take_column(infos, 'pcfg')
        df = pd.DataFrame.from_records(infos)
        df['cdfs'] = cdfs
        df['K'] = ut.take_column(pcfgs, 'K')
        import plottool as pt
        # groups = list(df.groupby(('dsize', 't_denc_pername')))
        df = df[df['K'] != 10]

        fig = pt.figure(fnum=1)
        groups = list(df.groupby(('dsize')))
        pnum_ = pt.make_pnum_nextgen(nCols=1, nSubplots=len(groups))
        for val, df_group in groups:
            # print('---')
            # print(df_group)
            relevant_df = df_group[['K', 'qsize', 'dsize', 't_dpername']]
            relevant_df = relevant_df.rename(columns={'t_dpername': 'dpername'})
            relevant_cfgs = [ut.order_dict_by(d, relevant_df.columns.tolist())
                             for d in relevant_df.to_dict('records')]
            nonvaried_kw, varied_kws = ut.partition_varied_cfg_list(relevant_cfgs)
            labels_ = [ut.get_cfg_lbl(kw)[1:] for kw in varied_kws]
            cdfs_ = df_group['cdfs'].values
            plot_cmcs(cdfs_, labels_, fnum=1, pnum=pnum_(), ymin=.5)
            ax = pt.gca()
            nonvaried_text = ut.get_cfg_lbl(nonvaried_kw)[1:]
            # ax.set_title(nonvaried_text)
            pt.relative_text('lowerleft', nonvaried_text, ax=ax)

        pt.adjust_subplots(top=.9, bottom=.1, left=.12, right=.9, hspace=.3, wspace=.2)
        fig.set_size_inches([W, H * 1.9])
        fpath = join(self.dpath, expt_name + '.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath

    def draw_all(self):
        """
        CommandLine:
            python -m ibeis Chap3.draw_all --dbs=GZ_Master1,PZ_Master1,GIRM_Master1

        Example:
            >>> # DISABLE_DOCTEST
            >>> from ibeis.scripts.thesis import *  # NOQA
            >>> dbname = ut.get_argval('--db', default='PZ_MTEST')
            >>> dbnames = ut.get_argval('--dbs', type_=list, default=[dbname])
            >>> for dbname in dbnames:
            >>>     print('dbname = %r' % (dbname,))
            >>>     self = Chap3(dbname)
            >>>     self.draw_all()
        """
        self.ensure_results()

        # if 'baseline' in self.expt_results:
        #     self.draw_baseline()

        if ('PZ' in self.dbname or 'GZ' in self.dbname):
            expts = ['foregroundness', 'invar', 'smk', 'nsum', 'kexpt']
            for expt_name in expts:
                if expt_name in self.expt_results:
                    try:
                        getattr(self, 'draw_' + expt_name)()
                    except KeyError:
                        getattr(self, 'measure_' + expt_name)()
                        getattr(self, 'draw_' + expt_name)()
            # if 'invar' in self.expt_results:
            #     self.draw_invar()
            # if 'smk' in self.expt_results:
            #     self.draw_smk()
            # if 'nsum' in self.expt_results:
            #     self.draw_nsum()
            # if 'kexpt' in self.expt_results:
            #     self.draw_kexpt()

    def draw_time_distri(self):
        """
        CommandLine:
            python -m ibeis Chap3.draw_time_distri --dbs=GZ_Master1,PZ_Master1,GIRM_MasterV
            python -m ibeis Chap3.draw_time_distri --dbs=GIRM_Master1
            python -m ibeis Chap3.draw_time_distri --dbs=GZ_Master1
            python -m ibeis Chap3.draw_time_distri --dbs=PZ_Master1
            python -m ibeis Chap3.draw_time_distri --dbs=humpbacks_fb

        Example:
            >>> # DISABLE_DOCTEST
            >>> from ibeis.scripts.thesis import *  # NOQA
            >>> dbname = ut.get_argval('--db', default='PZ_MTEST')
            >>> dbnames = ut.get_argval('--dbs', type_=list, default=[dbname])
            >>> for dbname in dbnames:
            >>>     print('dbname = %r' % (dbname,))
            >>>     self = Chap3(dbname)
            >>>     self.draw_time_distri()
        """
        import matplotlib as mpl
        mpl.rcParams.update(TMP_RC)
        if self.ibs is None:
            self._precollect()
        ibs = self.ibs
        annots = ibs.annots(self.aids_pool)
        images = ibs.images(set(annots.gids))
        unixtimes_ = images.unixtime_asfloat
        num_nan = np.isnan(unixtimes_).sum()
        num_total = len(unixtimes_)
        unixtimes = unixtimes_[~np.isnan(unixtimes_)]

        mintime = vt.safe_min(unixtimes)
        maxtime = vt.safe_max(unixtimes)
        unixtime_domain = np.linspace(mintime, maxtime, 1000)

        import matplotlib as mpl
        mpl.rcParams.update(TMP_RC)

        from sklearn.neighbors.kde import KernelDensity
        bw = ut.get_argval('--bw', default=None)
        day = 60 * 60 * 24
        if bw is not None:
            pass
        elif 'GIRM' in self.dbname:
            bw = day / 4
        elif 'GZ' in self.dbname:
            bw = day * 30
        elif 'PZ' in self.dbname:
            bw = day * 30
        elif 'humpbacks_fb' in self.dbname:
            bw = day * 30
        else:
            from sklearn.model_selection import RandomizedSearchCV
            space = np.linspace(day, day * 14, 14).tolist()
            grid_params = {'bandwidth': space}
            searcher = ut.partial(RandomizedSearchCV, n_iter=5, n_jobs=8)
            print('Searching for best bandwidth')
            grid = searcher(KernelDensity(kernel='gaussian'), grid_params,
                            cv=2, verbose=0)
            grid.fit(unixtimes[:, None])
            bw = grid.best_params_['bandwidth']
            print('bw = %r' % (bw,))
            print('bw(days) = %r' % (bw / day,))

        kde = KernelDensity(kernel='gaussian', bandwidth=bw)
        kde.fit(unixtimes[:, None])
        log_density = kde.score_samples(unixtime_domain[:, None])
        density = np.exp(log_density)
        ydata = density.copy()
        # emphasize smaller values
        ydata /= ydata.max()
        ydata = np.sqrt(ydata)
        xdata = unixtime_domain
        xdata_ts = ut.lmap(ut.unixtime_to_datetimeobj, xdata)

        pt.multi_plot(xdata_ts, [ydata], label_list=['time'],
                      alpha=.7, fnum=1, pnum=(1, 1, 1), ymin=0, fill=True,
                      marker='', xlabel='Date', ylabel='# images',
                      num_xticks=5,
                      use_legend=False)
        infos = []
        if num_nan > 0:
            infos.append('#nan={}'.format(num_nan))
            infos.append('#total={}'.format(num_total))
        else:
            infos.append('#total={}'.format(num_total))
        text = '\n'.join(infos)
        pt.relative_text((.02, .02), text, halign='left', valign='top')

        ax = pt.gca()
        fig = pt.gcf()
        ax.set_yticks([])
        if False:
            icon = ibs.get_database_icon()
            pt.overlay_icon(icon, coords=(0, 1), bbox_alignment=(0, 1),
                            as_artist=1, max_asize=(100, 200))
        pt.adjust_subplots(top=.9, bottom=.1, left=.12, right=.9)
        fig.set_size_inches([W, H * .4])
        fpath = join(self.dpath, 'timedist.png')
        vt.imwrite(fpath, pt.render_figure_to_image(fig, dpi=DPI))
        return fpath


@ut.reloadable_class
class Chap3(DBInputs, IOContract, Chap3Agg, Chap3Draw, Chap3Measures,
            Chap3Commands):
    base_dpath = ut.truepath('~/latex/crall-thesis-2017/figuresY')


class Sampler(object):

    @staticmethod
    def _same_occur_split(ibs, aids):
        """
            >>> from ibeis.scripts.thesis import *
            >>> self = Chap3('PZ_Master1')
            >>> self._precollect()
        """
        annots = ibs.annots(aids)
        # occurrences = ibs._annot_groups(annots.group(annots.occurrence_text)[1])
        encounters = ibs._annot_groups(annots.group(annots.encounter_text)[1])

        nid_to_splits = ut.ddict(list)
        # Find the biggest occurrences and pick an annotation from that
        # occurrence to be sampled
        occur_to_encs = ut.group_items(encounters, ut.take_column(encounters.occurrence_text, 0))
        occur_encs = ut.sortedby(list(occur_to_encs.values()), list(map(len, occur_to_encs.values())))[::-1]
        for encs in occur_encs:
            for enc in encs:
                sortx = ut.argsort(enc.qualities)[::-1]
                annot = enc[sortx[0]]
                if len(nid_to_splits[annot.nid]) < 2:
                    nid_to_splits[annot.nid].append(annot.aid)

        rng = ut.ensure_rng(0)
        pyrng = random.Random(rng.randint(sys.maxsize))

        qaids = []
        dname_encs = []
        confusor_pool = []
        for nid, aids_ in nid_to_splits.items():
            if len(aids_) < 2:
                confusor_pool.extend(aids_)
            else:
                pyrng.shuffle(aids_)
                qaids.append(aids_[0])
                dname_encs.append([[aids_[1]]])
        confusor_pool = ut.shuffle(confusor_pool, rng=0)
        return qaids, dname_encs, confusor_pool

    @staticmethod
    def _intra_enc(ibs, aids):
        # Make a query / database set for each occurrence
        # ibs = self.ibs
        # aids = self.aids_pool
        annots = ibs.annots(aids)
        # occurrences = ibs._annot_groups(annots.group(annots.occurrence_text)[1])
        encounters = ibs._annot_groups(annots.group(annots.encounter_text)[1])

        # rng = ut.ensure_rng(0)
        # pyrng = random.Random(rng.randint(sys.maxsize))

        # Find the biggest occurrences and pick an annotation from that
        # occurrence to be sampled
        occurrences = ut.group_items(encounters, ut.take_column(encounters.occurrence_text, 0))
        occurrences = ut.map_vals(ibs._annot_groups, occurrences)

        occur_nids = {o: set(ut.flatten(encs.nids))
                      for o, encs in occurrences.items()}

        # Need to find multiple disjoint exact covers of the nids
        # Greedy solution because this is NP-hard
        from ibeis.algo.graph import nx_dynamic_graph
        G = nx_dynamic_graph.DynConnGraph()
        G.add_nodes_from(occur_nids.keys())
        occur_ids = ut.sortedby(
            occur_nids.keys(), ut.lmap(len, occur_nids.values()))[::-1]
        current_combos = {frozenset(G.connected_to(o1)): occur_nids[o1]
                          for o1 in occur_ids}
        for o1, o2 in ut.combinations(occur_ids, 2):
            if G.node_label(o1) == G.node_label(o2):
                continue
            cc1 = frozenset(G.connected_to(o1))
            cc2 = frozenset(G.connected_to(o2))
            nids1 = current_combos[cc1]
            nids2 = current_combos[cc2]
            if nids1.isdisjoint(nids2):
                G.add_edge(o1, o2)
                del current_combos[cc1]
                del current_combos[cc2]
                current_combos[frozenset(cc1.union(cc2))] = nids1.union(nids2)

        # Pick the top few occurrence groups with the most names
        grouped_occurs = list(map(frozenset, G.connected_components()))
        group_size = ut.lmap(len, list(grouped_occurs))
        top_groups = ut.sortedby(grouped_occurs, group_size)[::-1][0:4]

        samples = []

        for os in top_groups:
            encs = ut.flatten(occurrences[o].aids for o in os)
            encs = ut.lmap(ibs.annots, encs)
            qaids = []
            daids = []
            for enc in encs:
                if len(enc) == 1:
                    daids.extend(enc.aids)
                else:
                    daids.extend(enc.aids)
                    qaids.extend(enc.aids)
            sample = SplitSample(qaids, daids)
            samples.append(sample)
        return samples

        #         nid = enc.nids[0]
        #         if len(nid_to_splits[nid]) == 0:
        #             chosen = pyrng.sample(enc.aids, min(len(enc), 2))
        #             nid_to_splits[nid].extend(chosen)

        #     qaids = []
        #     dname_encs = []
        #     confusor_pool = []
        #     for nid, aids_ in nid_to_splits.items():
        #         if len(aids_) < 2:
        #             confusor_pool.extend(aids_)
        #         else:
        #             pyrng.shuffle(aids_)
        #             qaids.append(aids_[0])
        #             dname_encs.append([[aids_[1]]])
        #     confusor_pool = ut.shuffle(confusor_pool, rng=0)
        #     self = ExpandingSample(qaids, dname_encs, confusor_pool)
        #     query_samples.append(self)
        # return query_samples

    @staticmethod
    def _same_enc_split(ibs, aids):
        """
            >>> from ibeis.scripts.thesis import *
            >>> self = Chap3('PZ_Master1')
            >>> self._precollect()
        """
        annots = ibs.annots(aids)
        # occurrences = ibs._annot_groups(annots.group(annots.occurrence_text)[1])
        encounters = ibs._annot_groups(annots.group(annots.encounter_text)[1])

        rng = ut.ensure_rng(0)
        pyrng = random.Random(rng.randint(sys.maxsize))

        nid_to_splits = ut.ddict(list)
        # Find the biggest occurrences and pick an annotation from that
        # occurrence to be sampled
        occur_to_encs = ut.group_items(encounters, ut.take_column(encounters.occurrence_text, 0))
        occur_encs = ut.sortedby(list(occur_to_encs.values()), list(map(len, occur_to_encs.values())))[::-1]
        for encs in occur_encs:
            for enc in encs:
                nid = enc.nids[0]
                if len(nid_to_splits[nid]) == 0:
                    chosen = pyrng.sample(enc.aids, min(len(enc), 2))
                    nid_to_splits[nid].extend(chosen)

        qaids = []
        dname_encs = []
        confusor_pool = []
        for nid, aids_ in nid_to_splits.items():
            if len(aids_) < 2:
                confusor_pool.extend(aids_)
            else:
                pyrng.shuffle(aids_)
                qaids.append(aids_[0])
                dname_encs.append([[aids_[1]]])
        confusor_pool = ut.shuffle(confusor_pool, rng=0)
        return qaids, dname_encs, confusor_pool

    def _rand_splits(ibs, aids, qenc_per_name, denc_per_name_, annots_per_enc):
        """ This can be used for cross validation """
        # Find a split of query/database encounters and confusors
        from ibeis.init.filter_annots import encounter_crossval
        enc_splits, nid_to_confusors = encounter_crossval(
            ibs, aids, qenc_per_name=1, annots_per_enc=1,
            denc_per_name=denc_per_name_, rebalance=True, rng=0, early=True)

        qname_encs, dname_encs = enc_splits[0]
        qaids = sorted(ut.flatten(ut.flatten(qname_encs)))
        confusor_pool = ut.flatten(ut.flatten(nid_to_confusors.values()))
        confusor_pool = ut.shuffle(confusor_pool, rng=0)
        return qaids, dname_encs, confusor_pool

    @staticmethod
    def _alt_splits(ibs, aids, qenc_per_name, denc_per_name_, annots_per_enc):
        """ This cannot be used for cross validation """
        # Group annotations by encounter
        # from ibeis.other import ibsfuncs
        # primary_view = ibsfuncs.get_primary_species_viewpoint(ibs.get_primary_database_species())

        annots = ibs.annots(aids)
        encounters = ibs._annot_groups(annots.group(annots.encounter_text)[1])
        enc_nids = ut.take_column(encounters.nids, 0)
        nid_to_encs = ut.group_items(encounters, enc_nids)
        rng = ut.ensure_rng(0)
        pyrng = random.Random(rng.randint(sys.maxsize))

        n_need = qenc_per_name + denc_per_name_

        confusor_encs = {}
        sample_splits = {}

        def choose_best(enc, num):
            if len(enc) > num:
                sortx = ut.argsort(enc.qualities)[::-1]
                subenc = enc.take(sortx[0:num])
            else:
                subenc = enc
            return subenc

        for nid, encs in nid_to_encs.items():
            if len(encs) < n_need:
                confusor_encs[nid] = encs
            else:
                # For each name choose a query / database encounter.
                chosen_encs = pyrng.sample(encs, n_need)
                ibs._annot_groups(chosen_encs).aids
                # Choose high quality annotations from each encounter
                best_subencs = [choose_best(enc, annots_per_enc) for
                                enc in chosen_encs]
                # ibs._annot_groups(best_subencs).aids
                qsubenc = [a.aids for a in best_subencs[0:qenc_per_name]]
                dsubenc = [a.aids for a in best_subencs[qenc_per_name:]]
                sample_splits[nid] = (qsubenc, dsubenc)

        # make confusor encounters subject to the same constraints
        confusor_pool = []
        confname_encs = []
        for encs in confusor_encs.values():
            # new
            # chosen_encs = pyrng.sample(encs, min(len(encs), denc_per_name_))
            # rand_subencs = [pyrng.sample(enc.aids, annots_per_enc)
            #                 for enc in chosen_encs]
            # confname_encs.append(rand_subencs)

            # old
            confusor_pool.extend(
                ut.flatten([enc[0:annots_per_enc].aids for enc in encs])
            )

        qaids = ut.total_flatten(ut.take_column(sample_splits.values(), 0))
        dname_encs = ut.take_column(sample_splits.values(), 1)
        return qaids, dname_encs, confname_encs, confusor_pool

    @staticmethod
    def _varied_inputs(ibs, aids, denc_per_name=[1], extra_dbsize_fracs=None,
                        method='alt'):
        """
        Vary num per name and total number of annots

        Example:
            >>> from ibeis.scripts.thesis import *  # NOQA
            >>> self = Chap3('PZ_Master1')
            >>> self._precollect()
            >>> ibs = self.ibs
            >>> aids = self.aids_pool
            >>> print('--------')
            >>> qaids, daids_list, info_list = self._varied_inputs(ibs, aids, [1], [1], method='same_occur')
            >>> print('qsize = %r' % (len(qaids),))
            >>> for info in info_list:
            >>>     print(ut.repr4(info))
            >>> print('--------')
            >>> qaids, daids_list, info_list = self._varied_inputs(ibs, aids, [1], [1], method='same_enc')
            >>> print('qsize = %r' % (len(qaids),))
            >>> for info in info_list:
            >>>     print(ut.repr4(info))
            >>> print('--------')
            >>> qaids, daids_list, info_list = self._varied_inputs(ibs, aids, [1, 2], [0])
            >>> print('qsize = %r' % (len(qaids),))
            >>> for info in info_list:
            >>>     print(ut.repr4(info))
            >>> print('--------')
            >>> qaids, daids_list, info_list = self._varied_inputs(ibs, aids, [3], [0, 1])
            >>> print('qsize = %r' % (len(qaids),))
            >>> for info in info_list:
            >>>     print(ut.repr4(info))

        Ignore:
            ibs, aids = self.ibs, self.aids_pool
            denc_per_name = 1
            denc_per_name = [1]
            extra_dbsize_fracs = None

            extra_dbsize_fracs = [0, .5, 1]
        """
        qenc_per_name = 1
        annots_per_enc = 1
        denc_per_name_ = max(denc_per_name)

        if method == 'alt':
            qaids, dname_encs, confname_encs, confusor_pool = Sampler._alt_splits(
                ibs, aids, qenc_per_name, denc_per_name_, annots_per_enc)
        elif method == 'same_occur':
            assert denc_per_name_ == 1
            assert annots_per_enc == 1
            assert qenc_per_name == 1
            qaids, dname_encs, confusor_pool = Sampler._same_occur_split(ibs, aids)
        elif method == 'same_enc':
            qaids, dname_encs, confusor_pool = Sampler._same_enc_split(ibs, aids)
        else:
            raise KeyError(method)

        # Vary the number of database encounters in each sample
        target_daids_list = []
        target_info_list_ = []
        for num in denc_per_name:
            dname_encs_ = ut.take_column(dname_encs, slice(0, num))
            dnames_ = ut.lmap(ut.flatten, dname_encs_)
            daids_ = ut.flatten(dnames_)
            target_daids_list.append(daids_)
            name_lens = ut.lmap(len, dnames_)
            dpername = (name_lens[0] if ut.allsame(name_lens) else
                        np.mean(name_lens))
            target_info_list_.append(ut.odict([
                ('qsize', len(qaids)),
                ('t_n_names', len(dname_encs_)),
                ('t_dpername', dpername),
                ('t_denc_pername', num),
                ('t_dsize', len(daids_)),
            ]))

        # confusor_names_matter = True
        # if confusor_names_matter:
        #     extra_pools = [
        #         ut.total_flatten(ut.take_column(confname_encs, slice(0, num)))
        #         for num in denc_per_name
        #     ]
        #     dbsize_list = ut.lmap(len, target_daids_list)
        #     max_dsize = max(dbsize_list)
        #     for num, daids_ in zip(denc_per_name, target_daids_list):
        #         num_take = max_dsize - len(daids_)
        #         print('num_take = %r' % (num_take,))

        #         confname_encs_ = ut.total_flatten(ut.take_column(confname_encs, slice(0, num)))
        #         confusor_pool_ = ut.total_flatten(confname_encs_)
        #         if num_take > len(confusor_pool_):
        #             # we need to siphon off valid queries to use them as
        #             # confusors
        #             raise AssertionError(
        #                 'have={}, need={}, not enough confusors for num={}'.format(
        #                     len(confusor_pool_), num_take, num
        #                 ))

        # Append confusors to maintain a constant dbsize in each base sample
        dbsize_list = ut.lmap(len, target_daids_list)
        max_dsize = max(dbsize_list)
        n_need = max_dsize - min(dbsize_list)
        n_extra_avail = len(confusor_pool) - n_need
        # assert len(confusor_pool) > n_need, 'not enough confusors'
        padded_daids_list = []
        padded_info_list_ = []
        for num, daids_, info_ in zip(denc_per_name, target_daids_list,
                                      target_info_list_):
            num_take = max_dsize - len(daids_)

            assert num_take < len(confusor_pool), 'not enough confusors'
            pad_aids = confusor_pool[:num_take]

            new_aids = daids_ + pad_aids
            info_ = info_.copy()
            info_['n_pad'] = len(pad_aids)
            info_['pad_dsize'] = len(new_aids)
            padded_info_list_.append(info_)
            padded_daids_list.append(new_aids)

        # Vary the dbsize by appending extra confusors
        if extra_dbsize_fracs is None:
            extra_dbsize_fracs = [1.]
        extra_fracs = np.array(extra_dbsize_fracs)
        n_extra_list = np.unique(extra_fracs * n_extra_avail).astype(np.int)
        daids_list = []
        info_list = []
        for n in n_extra_list:
            for daids_, info_ in zip(padded_daids_list, padded_info_list_):
                extra_aids = confusor_pool[len(confusor_pool) - n:]
                daids = sorted(daids_ + extra_aids)
                daids_list.append(daids)
                info = info_.copy()
                info['n_extra'] = len(extra_aids)
                info['dsize'] = len(daids)
                info_list.append(info)

        import pandas as pd
        verbose = 0
        if verbose:
            print(pd.DataFrame.from_records(info_list))
            print('#qaids = %r' % (len(qaids),))
            print('num_need = %r' % (n_need,))
            print('max_dsize = %r' % (max_dsize,))
            if False:
                for daids in daids_list:
                    ibs.print_annotconfig_stats(qaids, daids)
        return qaids, daids_list, info_list
    pass


class SplitSample(ut.NiceRepr):
    def __init__(sample, qaids, daids):
        sample.qaids = qaids
        sample.daids = daids

    def __nice__(sample):
        return 'nQaids={}, nDaids={}'.format(
            len(sample.qaids), len(sample.daids)
        )


class ExpandingSample(ut.NiceRepr):
    def __init__(sample, qaids, dname_encs, confusor_pool):
        sample.qaids = qaids
        sample.dname_encs = dname_encs
        sample.confusor_pool = confusor_pool

    def __nice__(sample):
        denc_pername = ut.lmap(len, sample.dname_encs)
        n_denc_pername = np.mean(denc_pername)
        return 'nQaids={}, nDEncPerName={}, nConfu={}'.format(
            len(sample.qaids), n_denc_pername, len(sample.confusor_pool)
        )

    def expand(sample, denc_per_name=[1], extra_dbsize_fracs=[0]):
        # Vary the number of database encounters in each sample
        target_daids_list = []
        target_info_list_ = []
        for num in denc_per_name:
            dname_encs_ = ut.take_column(sample.dname_encs, slice(0, num))
            dnames_ = ut.lmap(ut.flatten, dname_encs_)
            daids_ = ut.total_flatten(dname_encs_)
            target_daids_list.append(daids_)
            name_lens = ut.lmap(len, dnames_)
            dpername = (name_lens[0] if ut.allsame(name_lens) else
                        np.mean(name_lens))
            target_info_list_.append(ut.odict([
                ('qsize', len(sample.qaids)),
                ('t_n_names', len(dname_encs_)),
                ('t_dpername', dpername),
                ('t_denc_pername', num),
                ('t_dsize', len(daids_)),
            ]))

        # Append confusors to maintain a constant dbsize in each base sample
        dbsize_list = ut.lmap(len, target_daids_list)
        max_dsize = max(dbsize_list)
        n_need = max_dsize - min(dbsize_list)
        n_extra_avail = len(sample.confusor_pool) - n_need
        assert len(sample.confusor_pool) > n_need, 'not enough confusors'
        padded_daids_list = []
        padded_info_list_ = []
        for daids_, info_ in zip(target_daids_list, target_info_list_):
            num_take = max_dsize - len(daids_)
            pad_aids = sample.confusor_pool[:num_take]
            new_aids = daids_ + pad_aids
            info_ = info_.copy()
            info_['n_pad'] = len(pad_aids)
            info_['pad_dsize'] = len(new_aids)
            padded_info_list_.append(info_)
            padded_daids_list.append(new_aids)

        # Vary the dbsize by appending extra confusors
        if extra_dbsize_fracs is None:
            extra_dbsize_fracs = [1.]
        extra_fracs = np.array(extra_dbsize_fracs)
        n_extra_list = np.unique(extra_fracs * n_extra_avail).astype(np.int)
        daids_list = []
        info_list = []
        for n in n_extra_list:
            for daids_, info_ in zip(padded_daids_list, padded_info_list_):
                extra_aids = sample.confusor_pool[len(sample.confusor_pool) - n:]
                daids = sorted(daids_ + extra_aids)
                daids_list.append(daids)
                info = info_.copy()
                info['n_extra'] = len(extra_aids)
                info['dsize'] = len(daids)
                info_list.append(info)

        import pandas as pd
        verbose = 0
        if verbose:
            print(pd.DataFrame.from_records(info_list))
            print('#qaids = %r' % (len(sample.qaids),))
            print('num_need = %r' % (n_need,))
            print('max_dsize = %r' % (max_dsize,))
        return sample.qaids, daids_list, info_list


def _ranking_hist(ibs, qaids, daids, cfgdict):
    # Execute the ranking algorithm
    qaids = sorted(qaids)
    daids = sorted(daids)
    qreq_ = ibs.new_query_request(qaids, daids, cfgdict=cfgdict)
    cm_list = qreq_.execute()
    cm_list = [cm.extend_results(qreq_) for cm in cm_list]
    name_ranks = [cm.get_name_ranks([cm.qnid])[0] for cm in cm_list]
    # Measure rank probabilities
    bins = np.arange(len(qreq_.dnids))
    hist = np.histogram(name_ranks, bins=bins)[0]
    return hist


def _ranking_cdf(ibs, qaids, daids, cfgdict):
    hist = _ranking_hist(ibs, qaids, daids, cfgdict)
    cdf = (np.cumsum(hist) / sum(hist))
    return cdf


def label_alias(k):
    k = k.replace('True', 'T')
    k = k.replace('False', 'F')
    return k


def feat_alias(k):
    # presentation values for feature dimension
    # k = k.replace('weighted_', 'wgt_')
    # k = k.replace('norm_x', 'x')
    # k = k.replace('norm_y', 'y')
    # k = k.replace('yaw', 'view')
    return k


def find_minority_class_ccs(infr):
    # Finds ccs involved in photobombs and incomparble cases
    pb_edges = [
        edge for edge, tags in infr.gen_edge_attrs('tags')
        if 'photobomb'in tags
    ]
    incomp_edges = list(infr.incomp_graph.edges())
    minority_edges = pb_edges + incomp_edges
    minority_nids = set(infr.node_labels(*set(ut.flatten(minority_edges))))
    minority_ccs = [infr.pos_graph._ccs[nid] for nid in minority_nids]
    return minority_ccs


def test_mcc():
    num = 100
    xdata = np.linspace(0, 1, num * 2)
    ydata = np.linspace(1, -1, num * 2)
    pt.plt.plot(xdata, ydata, '--k',
                label='linear')

    y_true = [1] * num + [0] * num
    y_pred = y_true[:]
    import sklearn.metrics
    xs = []
    for i in range(0, len(y_true)):
        y_pred[-i] = 1 - y_pred[-i]
        xs.append(sklearn.metrics.matthews_corrcoef(y_true, y_pred))

    import plottool as pt
    pt.plot(xdata, xs, label='change one class at a time')

    y_true = ut.flatten(zip([1] * num, [0] * num))
    y_pred = y_true[:]
    import sklearn.metrics
    xs = []
    for i in range(0, len(y_true)):
        y_pred[-i] = 1 - y_pred[-i]
        xs.append(sklearn.metrics.matthews_corrcoef(y_true, y_pred))

    pt.plot(xdata, xs, label='change classes evenly')
    pt.gca().legend()


def prepare_cdfs(cdfs, labels):
    cdfs = vt.pad_vstack(cdfs, fill_value=1)
    # Sort so the best is on top
    sortx = np.lexsort(cdfs.T[::-1])[::-1]
    cdfs = cdfs[sortx]
    labels = ut.take(labels, sortx)
    return cdfs, labels


def plot_cmcs(cdfs, labels, fnum=1, pnum=(1, 1, 1), ymin=.4):
    cdfs, labels = prepare_cdfs(cdfs, labels)
    # Truncte to 20 ranks
    num_ranks = min(cdfs.shape[-1], 20)
    xdata = np.arange(1, num_ranks + 1)
    cdfs_trunc = cdfs[:, 0:num_ranks]
    label_list = ['%6.2f%% - %s' % (cdf[0] * 100, lbl)
                  for cdf, lbl in zip(cdfs_trunc, labels)]

    # ymin = .4
    num_yticks = (10 - int(ymin * 10)) + 1

    pt.multi_plot(
        xdata, cdfs_trunc, label_list=label_list,
        xlabel='rank', ylabel='match probability',
        use_legend=True, legend_loc='lower right', num_yticks=num_yticks,
        ymax=1, ymin=ymin, ypad=.005, xmin=.9, num_xticks=5,
        xmax=num_ranks + 1 - .5,
        pnum=pnum, fnum=fnum,
        rcParams=TMP_RC,
    )


def plot_cmcs2(cdfs, labels, fnum=1, **kwargs):
    fig = pt.figure(fnum=fnum)
    plot_cmcs(cdfs, labels, fnum=fnum, **kwargs)
    pt.adjust_subplots(top=.8, bottom=.2, left=.12, right=.9)
    fig.set_size_inches([W, H])
    return fig


# NEED FOR OLD PICKLES
class ExptChapter4(object):
    pass


if __name__ == '__main__':
    r"""
    CommandLine:
        python -m ibeis.scripts.thesis
        python -m ibeis.scripts.thesis --allexamples
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
