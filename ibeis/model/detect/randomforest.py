from __future__ import absolute_import, division, print_function
# Python
#from os.path import exists, join, split  # UNUSED
from os.path import splitext, exists
# UTool
from six.moves import zip, map, range
import utool
from vtool import image as gtool
from ibeis.model.detect import grabmodels
import pyrf
(print, print_, printDBG, rrr, profile) = utool.inject(
    __name__, '[randomforest]', DEBUG=False)


#=================
# IBEIS INTERFACE
#=================


def generate_detections(ibs, gid_list, species, **detectkw):
    """ detectkw can be: save_detection_images, save_scales, draw_supressed,
        detection_width, detection_height, percentage_left, percentage_top,
        nms_margin_percentage

        Yeilds tuples of image ids and bounding boxes
    """
    #
    # Resize to a standard image size prior to detection
    src_gpath_list = list(map(str, ibs.get_image_detectpaths(gid_list)))
    utool.close_pool()

    # Get sizes of the original and resized images for final scale correction
    neww_list = [gtool.open_image_size(gpath)[0] for gpath in src_gpath_list]
    oldw_list = [oldw for (oldw, oldh) in ibs.get_image_sizes(gid_list)]
    scale_list = [oldw / neww for oldw, neww in zip(oldw_list, neww_list)]

    # Detect on scaled images
    ibs.cfg.other_cfg.ensure_attr('detect_use_chunks', True)
    use_chunks = ibs.cfg.other_cfg.detect_use_chunks

    generator = detect_species_bboxes(src_gpath_list, species,
                                      use_chunks=use_chunks, **detectkw)

    for gid, scale, (bboxes, confidences, img_conf) in zip(gid_list, scale_list, generator):
        # Unscale results
        unscaled_bboxes = [_scale_bbox(bbox_, scale) for bbox_ in bboxes]
        for index in range(len(unscaled_bboxes)):
            bbox = unscaled_bboxes[index]
            confidence = float(confidences[index])
            yield gid, bbox, confidence, img_conf


def get_image_hough_gpaths(ibs, gid_list, species, quick=True):
    detectkw = {
        'quick': quick,
        'save_detection_images': True,
        'save_scales': True,
    }
    #
    # Resize to a standard image size prior to detection
    src_gpath_list = list(map(str, ibs.get_image_detectpaths(gid_list)))
    dst_gpath_list = [splitext(gpath)[0] for gpath in src_gpath_list]
    hough_gpath_list = [gpath + '_hough.png' for gpath in dst_gpath_list]
    isvalid_list = [exists(gpath) for gpath in hough_gpath_list]

    # Need to recompute hough images for these gids
    dirty_gids = utool.get_dirty_items(gid_list, isvalid_list)
    num_dirty = len(dirty_gids)
    if num_dirty > 0:
        print('[detect.rf] making hough images for %d images' % num_dirty)
        detect_gen = generate_detections(ibs, dirty_gids, species, **detectkw)
        # Execute generator
        for tup in detect_gen:
            pass

    return hough_gpath_list


#=================
# HELPER FUNCTIONS
#=================


def _scale_bbox(bbox, s):
    bbox_scaled = (s * _ for _ in bbox)
    bbox_round = list(map(round, bbox_scaled))
    bbox_int   = list(map(int,   bbox_round))
    bbox2      = tuple(bbox_int)
    return bbox2


def _get_detector(species, quick=True):
    # Ensure all models downloaded and accounted for
    grabmodels.ensure_models()
    # Create detector
    if quick:
        config = {}
    else:
        config = {
            'scales': '11 2.0 1.75 1.5 1.33 1.15 1.0 0.75 0.55 0.40 0.30 0.20'
        }
    detector = pyrf.Random_Forest_Detector(rebuild=False, **config)
    trees_path = grabmodels.get_species_trees_paths(species)
    # Load forest, so we don't have to reload every time
    forest = detector.load(trees_path, species + '-')
    return detector, forest


def _get_detect_config(**detectkw):
    detect_config = {
        'percentage_top':    0.40,
    }
    detect_config.update(detectkw)
    return detect_config


#=================
# PYRF INTERFACE
#=================


def detect_species_bboxes(src_gpath_list, species, quick=True, use_chunks=False, **detectkw):
    """
    Generates bounding boxes for each source image
    For each image yeilds a list of bounding boxes
    """
    nImgs = len(src_gpath_list)
    print('[detect.rf] Begining %s detection' % (species,))
    detect_lbl = 'detect %s ' % species
    mark_prog, end_prog = utool.progress_func(nImgs, detect_lbl, flush_after=1)

    detect_config = _get_detect_config(**detectkw)
    detector, forest = _get_detector(species, quick=quick)
    detector.set_detect_params(**detect_config)

    dst_gpath_list = [splitext(gpath)[0] for gpath in src_gpath_list]
    # FIXME: Doing this in a generator may cause unnecessary page-faults
    # Maybe there is a better way of doing this, or generating results
    # in batch. It could be a utool batch serial process

    chunksize = 8
    use_chunks_ = use_chunks and nImgs >= chunksize

    if use_chunks_:
        print('[rf] detect in chunks')
        pathtup_iter = list(zip(src_gpath_list, dst_gpath_list))
        for ic, chunk in enumerate(utool.ichunks(pathtup_iter, chunksize)):
            src_gpath_list = [tup[0] for tup in chunk]
            dst_gpath_list = [tup[1] for tup in chunk]
            mark_prog(ic * chunksize)
            results_list = detector.detect_many(forest, src_gpath_list, dst_gpath_list)

            for results in results_list:
                bboxes = [(minx, miny, (maxx - minx), (maxy - miny))
                          for (centx, centy, minx, miny, maxx, maxy, confidence, supressed)
                          in results if supressed == 0]

                #x_arr = results[:, 2]
                #y_arr = results[:, 3]
                #w_arr = results[:, 4] - results[:, 2]
                #h_arr = results[:, 5] - results[:, 3]
                #bboxes = np.hstack((x_arr, y_arr, w_arr, h_arr))
                # Unpack unsupressed bounding boxes

                confidences = [confidence
                               for (centx, centy, minx, miny, maxx, maxy, confidence, supressed)
                               in results if supressed == 0]

                if len(results) > 0:
                    image_confidence = max([float(result[6]) for result in results])
                else:
                    image_confidence = 0.0

                yield bboxes, confidences, image_confidence
    else:
        print('[rf] detect one image at a time')
        pathtup_iter = zip(src_gpath_list, dst_gpath_list)
        for ix, (src_gpath, dst_gpath) in enumerate(pathtup_iter):
            mark_prog(ix)
            results = detector.detect(forest, src_gpath, dst_gpath)
            bboxes = [(minx, miny, (maxx - minx), (maxy - miny))
                      for (centx, centy, minx, miny, maxx, maxy, confidence, supressed)
                      in results if supressed == 0]

            confidences = [confidence
                           for (centx, centy, minx, miny, maxx, maxy, confidence, supressed)
                           in results if supressed == 0]

            if len(results) > 0:
                image_confidence = max([float(result[6]) for result in results])
            else:
                image_confidence = 0.0

            yield bboxes, confidences, image_confidence
    end_prog()
