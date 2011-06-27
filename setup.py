#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distribute_setup import use_setuptools
    use_setuptools()
    from setuptools import setup

import os
import sys

from ConfigParser import ConfigParser

from pkg_resources import (parse_requirements, working_set, safe_name,
                           safe_version)
from distutils import log
from distutils.command.build import build as _build
from distutils.command.clean import clean as _clean
from setuptools.command.develop import develop as _develop
from setuptools.command.install import install as _install

try:
    from nose.commands import nosetests as _nosetests
except ImportError:
    _nosetests = None


SUBDIST_DIRS = None


SUBDISTS = None


# TODO: Move most of this stuff into stsci.distutils; have it imported from
# there (have to add stsci.distutils to sys.path first, but that can be
# hard-coded and if it doesn't work nothing else will anyways)


def get_subdist_dirs():
    global SUBDIST_DIRS
    if SUBDIST_DIRS is None:
        SUBDIST_DIRS = [p for p in os.listdir('.')
                        if os.path.isdir(p) and
                        os.path.exists(os.path.join(p, 'setup.cfg'))]
    return SUBDIST_DIRS


def get_subdists():
    global SUBDISTS
    if SUBDISTS is None:
        SUBDISTS = {}
        for subdist_dir in get_subdist_dirs():
            setup_cfg = ConfigParser()
            setup_cfg.read(os.path.join(subdist_dir, 'setup.cfg'))
            if not setup_cfg.has_section('metadata'):
                continue
            elif not setup_cfg.has_option('metadata', 'name'):
                continue

            # safe_name ensures that the name will appear the same as the
            # pkg_resources requirement parser's normalization
            name = safe_name(setup_cfg.get('metadata', 'name'))

            if setup_cfg.has_option('metadata', 'version'):
                version = safe_version(setup_cfg.get('metadata', 'version'))
                subdist = (name, version)
            else:
                subdist = (name, None)

            SUBDISTS[subdist] = subdist_dir
    return SUBDISTS


# TODO: Whenever we switch to pure distutils2 this will have to be modified
def run_subdists_command(command, execsetup=None):
    requirements = parse_requirements(command.distribution.install_requires)
    for requirement in requirements:
        for subdist, subdist_dir in get_subdists().iteritems():
            subdist_name, subdist_version = subdist
            if subdist_name != requirement.project_name:
                continue
            if subdist_version not in requirement:
                # This checks that the minimum required version is met (or the
                # exact version, if the requirement is exact)
                continue
            # Okay, we have a matching subdistribution
            old_cwd = os.getcwd()
            os.chdir(subdist_dir)
            # Run the sub-distribution's setup.py with the same arguments that
            # were given the main dist's setup.py.
            try:
                log.info("running %s command in %s"
                         % (command.get_command_name(),
                            os.path.join(os.path.curdir, subdist_dir)))
                if '' not in sys.path:
                    sys.path.insert(0, '')
                if execsetup is None:
                    execfile(os.path.abspath('setup.py'))
                else:
                    execsetup()
            finally:
                os.chdir(old_cwd)
            break
        else:
            log.info('%s not found in sub-package distributions; skipping '
                     '%s...' % (requirement, command.get_command_name()))


# TODO: It might be nice to be able to wrap several command classes in a loop;
# in almost all cases except install this is doable.
class build(_build):
    def run(self):
        run_subdists_command(self)
        _build.run(self)


class clean(_clean):
    def run(self):
        run_subdists_command(self)
        _clean.run(self)


class develop(_develop):
    def run(self):
        # Here too it works best to call setup.py develop in a separate process
        def execsetup():
            try:
                os.system(' '.join(sys.argv))
            except SystemExit:
                pass
        run_subdists_command(self, execsetup=execsetup)
        # Don't run develop for the stsci_python package itself; there's
        # nothing really to develop *on*.  And it gets confused here when
        # processing dependencies, because none of the develop mode
        # distributions have been added to the default working set
        # TODO: Find a way to fix the working set problem.
        #_develop.run(self)


class install(_install):
    def run(self):
        install_lib = self.distribution.get_command_obj('install_lib')
        install_scripts = self.distribution.get_command_obj('install_scripts')
        install_cmd = self.distribution.get_command_obj('install')
        for cmd in (install_lib, install_scripts, install_cmd):
            cmd.ensure_finalized()

        # These are some options that will probably end up being passed to
        # easy_install in execsetup; ensure that the paths are absolute so we
        # don't get lost
        opts = {'prefix': install_cmd.prefix,
                'install-dir': install_lib.install_dir,
                'script-dir': install_scripts.install_dir,
                'record': install_cmd.record}
        for optname, value in opts.items():
            if value is not None:
                opts[optname] = os.path.abspath(value)
        opts['optimize'] = install_lib.optimize


        def execsetup(opts=opts):
            try:
                argv = sys.argv[:]
                if ('--root' not in sys.argv and
                    '--old-and-unmanageable' not in sys.argv and
                    '--single-version-externally-managed' not in sys.argv):
                    # Use easy_install to install instead; that way we can have
                    # more control over things like disabling dependency
                    # checking
                    # 'build' is inserted before 'easy_install' since the
                    # easy_install command by itself seems to squelch much of
                    # the build output
                    argv = [argv[0], 'build', 'easy_install', '--no-deps']
                    # Now, set the install-dir option from the install_lib
                    # command which, according to comments in the distribute
                    # source code "takes into account --prefix and --home and
                    # all that other crud"; set some other options as well
                    for optname, value in opts.iteritems():
                        if value is not None:
                            argv.append('--%s=%s' % (optname, value))

                    argv.append('.')

                os.system(' '.join(argv))
            except SystemExit:
                pass
        run_subdists_command(self, execsetup=execsetup)
        if self.old_and_unmanageable or self.single_version_externally_managed:
            _install.run(self)
        else:
            self.do_egg_install()


if _nosetests:
    class nosetests(_nosetests):
        def run(self):
            def execsetup():
                try:
                    # It's necessary to call os.system to run each project's tests
                    # in its own process; otherwise the tests interfere with each
                    # other too much, even if --with-isolation is used
                    os.system(' '.join(sys.argv))
                except SystemExit:
                    pass
            run_subdists_command(self, execsetup=execsetup)
            _nosetests.run(self)


CUSTOM_COMMANDS = {'build': build, 'clean': clean, 'develop': develop,
                   'install': install}
if 'nosetests' in globals():
    CUSTOM_COMMANDS['nosetests'] = nosetests


setup(
    setup_requires=['d2to1>=0.2.2'],
    d2to1=True,
    use_2to3=True,
    cmdclass=CUSTOM_COMMANDS
)
