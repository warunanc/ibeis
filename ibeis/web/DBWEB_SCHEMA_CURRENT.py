# AUTOGENERATED ON 11:49:37 2014/11/09
from __future__ import absolute_import, division, print_function
from ibeis import constants


# =======================
# Schema Version Current
# =======================


VERSION_CURRENT = '1.0.0'


def update_current(db, ibs=None):
    db.add_table(constants.METADATA_TABLE, (
        ('metadata_rowid',               'INTEGER PRIMARY KEY'),
        ('metadata_key',                 'TEXT'),
        ('metadata_value',               'TEXT'),
    ),
        superkey_colnames=['metadata_key'],
        docstr='''
        The table that stores permanently all of the metadata about the
        database (tables, etc)''')

    db.add_table('reviews', (
        ('review_rowid',                 'INTEGER PRIMARY KEY'),
        ('image_rowid',                  'INTEGER'),
        ('review_count',                 'INTEGER DEFAULT 0'),
    ),
        superkey_colnames=['image_rowid'],
        docstr='''
        SQLite table to store the web state for detection review''')

    db.add_table('viewpoints', (
        ('viewpoint_rowid',              'INTEGER PRIMARY KEY'),
        ('annot_rowid',                  'INTEGER'),
        ('viewpoint_value_1',            'INTEGER DEFAULT -1'),
        ('viewpoint_value_2',            'INTEGER DEFAULT -1'),
        ('viewpoint_value_avg',          'INTEGER DEFAULT -1'),
    ),
        superkey_colnames=['annot_rowid'],
        docstr='''
        SQLite table to store the web state for viewpoint turking''')
