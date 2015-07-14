from .. import util
from .impl import DefaultImpl

#from sqlalchemy.ext.compiler import compiles
#from .base import AddColumn, alter_table
#from sqlalchemy.schema import AddConstraint


class VirtuosoImpl(DefaultImpl):
    __dialect__ = 'virtuoso'

    transactional_ddl = True
