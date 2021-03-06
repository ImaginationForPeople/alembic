.. _alembic.autogenerate.toplevel:

==============
Autogeneration
==============

The autogenerate system has two areas of API that are public:

1. The ability to do a "diff" of a :class:`~sqlalchemy.schema.MetaData` object against
   a database, and receive a data structure back.  This structure
   is available either as a rudimentary list of changes, or as
   a :class:`.MigrateOperation` structure.

2. The ability to alter how the ``alembic revision`` command generates
   revision scripts, including support for multiple revision scripts
   generated in one pass.

Getting Diffs
==============

.. autofunction:: alembic.autogenerate.compare_metadata

.. autofunction:: alembic.autogenerate.produce_migrations

.. _customizing_revision:

Customizing Revision Generation
==========================================

.. versionadded:: 0.8.0 - the ``alembic revision`` system is now customizable.

The ``alembic revision`` command, also available programmatically
via :func:`.command.revision`, essentially produces a single migration
script after being run.  Whether or not the ``--autogenerate`` option
was specified basically determines if this script is a blank revision
script with empty ``upgrade()`` and ``downgrade()`` functions, or was
produced with alembic operation directives as the result of autogenerate.

In either case, the system creates a full plan of what is to be done
in the form of a :class:`.MigrateOperation` structure, which is then
used to produce the script.

For example, suppose we ran ``alembic revision --autogenerate``, and the
end result was that it produced a new revision ``'eced083f5df'``
with the following contents::

    """create the organization table."""

    # revision identifiers, used by Alembic.
    revision = 'eced083f5df'
    down_revision = 'beafc7d709f'

    from alembic import op
    import sqlalchemy as sa


    def upgrade():
        op.create_table(
            'organization',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(50), nullable=False)
        )
        op.add_column(
            'user',
            sa.Column('organization_id', sa.Integer())
        )
        op.create_foreign_key(
            'org_fk', 'user', 'organization', ['organization_id'], ['id']
        )

    def downgrade():
        op.drop_constraint('org_fk', 'user')
        op.drop_column('user', 'organization_id')
        op.drop_table('organization')

The above script is generated by a :class:`.MigrateOperation` structure
that looks like this::

    from alembic.operations import ops
    import sqlalchemy as sa

    migration_script = ops.MigrationScript(
        'eced083f5df',
        ops.UpgradeOps(
            ops=[
                ops.CreateTableOp(
                    'organization',
                    [
                        sa.Column('id', sa.Integer(), primary_key=True),
                        sa.Column('name', sa.String(50), nullable=False)
                    ]
                ),
                ops.ModifyTableOps(
                    'user',
                    ops=[
                        ops.AddColumnOp(
                            'user',
                            sa.Column('organization_id', sa.Integer())
                        ),
                        ops.CreateForeignKeyOp(
                            'org_fk', 'user', 'organization',
                            ['organization_id'], ['id']
                        )
                    ]
                )
            ]
        ),
        ops.DowngradeOps(
            ops=[
                ops.ModifyTableOps(
                    'user',
                    ops=[
                        ops.DropConstraintOp('org_fk', 'user'),
                        ops.DropColumnOp('user', 'organization_id')
                    ]
                ),
                ops.DropTableOp('organization')
            ]
        ),
        message='create the organization table.'
    )

When we deal with a :class:`.MigrationScript` structure, we can render
the upgrade/downgrade sections into strings for debugging purposes
using the :func:`.render_python_code` helper function::

    from alembic.autogenerate import render_python_code
    print(render_python_code(migration_script.upgrade_ops))

Renders::

    ### commands auto generated by Alembic - please adjust! ###
        op.create_table('organization',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.add_column('user', sa.Column('organization_id', sa.Integer(), nullable=True))
        op.create_foreign_key('org_fk', 'user', 'organization', ['organization_id'], ['id'])
        ### end Alembic commands ###

Given that structures like the above are used to generate new revision
files, and that we'd like to be able to alter these as they are created,
we then need a system to access this structure when the
:func:`.command.revision` command is used.  The
:paramref:`.EnvironmentContext.configure.process_revision_directives`
parameter gives us a way to alter this.   This is a function that
is passed the above structure as generated by Alembic, giving us a chance
to alter it.
For example, if we wanted to put all the "upgrade" operations into
a certain branch, and we wanted our script to not have any "downgrade"
operations at all, we could build an extension as follows, illustrated
within an ``env.py`` script::

    def process_revision_directives(context, revision, directives):
        script = directives[0]

        # set specific branch
        script.head = "mybranch@head"

        # erase downgrade operations
        script.downgrade_ops.ops[:] = []

    # ...

    def run_migrations_online():

        # ...
        with engine.connect() as connection:

            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                process_revision_directives=process_revision_directives)

            with context.begin_transaction():
                context.run_migrations()

Above, the ``directives`` argument is a Python list.  We may alter the
given structure within this list in-place, or replace it with a new
structure consisting of zero or more :class:`.MigrationScript` directives.
The :func:`.command.revision` command will then produce scripts corresponding
to whatever is in this list.

.. autofunction:: alembic.autogenerate.render_python_code

Autogenerating Custom Operation Directives
==========================================

In the section :ref:`operation_plugins`, we talked about adding new
subclasses of :class:`.MigrateOperation` in order to add new ``op.``
directives.  In the preceding section :ref:`customizing_revision`, we
also learned that these same :class:`.MigrateOperation` structures are at
the base of how the autogenerate system knows what Python code to render.
How to connect these two systems, so that our own custom operation
directives can be used?  First off, we'd probably be implementing
a :paramref:`.EnvironmentContext.configure.process_revision_directives`
plugin as described previously, so that we can add our own directives
to the autogenerate stream.  What if we wanted to add our ``CreateSequenceOp``
to the autogenerate structure?  We basically need to define an autogenerate
renderer for it, as follows::

    # note: this is a continuation of the example from the
    # "Operation Plugins" section

    from alembic.autogenerate import renderers

    @renderers.dispatch_for(CreateSequenceOp)
    def render_create_sequence(autogen_context, op):
        return "op.create_sequence(%r, **%r)" % (
            op.sequence_name,
            op.kw
        )

With our render function established, we can our ``CreateSequenceOp``
generated in an autogenerate context using the :func:`.render_python_code`
debugging function in conjunction with an :class:`.UpgradeOps` structure::

    from alembic.operations import ops
    from alembic.autogenerate import render_python_code

    upgrade_ops = ops.UpgradeOps(
        ops=[
            CreateSequenceOp("my_seq")
        ]
    )

    print(render_python_code(upgrade_ops))

Which produces::

    ### commands auto generated by Alembic - please adjust! ###
        op.create_sequence('my_seq', **{})
        ### end Alembic commands ###

