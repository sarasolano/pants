# coding=utf-8
# Copyright 2014 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

import json
import os
from textwrap import dedent

from pants.backend.core.register import build_file_aliases as register_core
from pants.backend.core.targets.dependencies import Dependencies
from pants.backend.core.targets.resources import Resources
from pants.backend.jvm.register import build_file_aliases as register_jvm
from pants.backend.jvm.targets.jar_dependency import JarDependency
from pants.backend.jvm.targets.jar_library import JarLibrary
from pants.backend.jvm.targets.java_library import JavaLibrary
from pants.backend.jvm.targets.java_tests import JavaTests
from pants.backend.jvm.targets.jvm_app import JvmApp
from pants.backend.jvm.targets.jvm_binary import JvmBinary
from pants.backend.jvm.targets.jvm_target import JvmTarget
from pants.backend.jvm.targets.scala_library import ScalaLibrary
from pants.backend.project_info.tasks.depmap import Depmap
from pants.backend.python.register import build_file_aliases as register_python
from pants.base.exceptions import TaskError
from pants_test.tasks.task_test_base import ConsoleTaskTestBase


class BaseDepmapTest(ConsoleTaskTestBase):
  @classmethod
  def task_type(cls):
    return Depmap


class DepmapTest(BaseDepmapTest):
  @property
  def alias_groups(self):
    return register_core().merge(register_jvm()).merge(register_python())

  def setUp(self):
    super(DepmapTest, self).setUp()

    def add_to_build_file(path, name, type, deps=(), **kwargs):
      self.add_to_build_file(path, dedent("""
          {type}(name='{name}',
            dependencies=[{deps}],
            {extra}
          )
          """.format(
        type=type,
        name=name,
        deps=','.join("pants('{0}')".format(dep) for dep in list(deps)),
        extra=('' if not kwargs else ', '.join('{0}={1}'.format(k, v) for k, v in kwargs.items()))
      )))

    def create_python_binary_target(path, name, entry_point, type, deps=()):
      self.add_to_build_file(path, dedent("""
          {type}(name='{name}',
            entry_point='{entry_point}',
            dependencies=[{deps}]
          )
          """.format(
        type=type,
        entry_point=entry_point,
        name=name,
        deps=','.join("pants('{0}')".format(dep) for dep in list(deps)))
      ))

    def create_jvm_app(path, name, type, binary, deps=()):
      self.add_to_build_file(path, dedent("""
          {type}(name='{name}',
            dependencies=[pants('{binary}')],
            bundles={deps}
          )
          """.format(
        type=type,
        name=name,
        binary=binary,
        deps=deps)
      ))

    add_to_build_file('common/a', 'a', 'target')
    add_to_build_file('common/b', 'b', 'jar_library')
    self.add_to_build_file('common/c', dedent("""
      java_library(name='c',
        sources=[],
      )
    """))
    add_to_build_file('common/d', 'd', 'python_library')
    create_python_binary_target('common/e', 'e', 'common.e.entry', 'python_binary')
    add_to_build_file('common/f', 'f', 'jvm_binary')
    add_to_build_file('common/g', 'g', 'jvm_binary', deps=['common/f:f'])
    self.create_dir('common/h')
    self.create_file('common/h/common.f')
    create_jvm_app('common/h', 'h', 'jvm_app', 'common/f:f', "[bundle(fileset='common.f')]")
    self.create_dir('common/i')
    self.create_file('common/i/common.g')
    create_jvm_app('common/i', 'i', 'jvm_app', 'common/g:g', "[bundle(fileset='common.g')]")
    add_to_build_file('overlaps', 'one', 'jvm_binary', deps=['common/h', 'common/i'])
    self.add_to_build_file('overlaps', dedent("""
      java_library(name='two',
        dependencies=[pants('overlaps:one')],
        sources=[],
      )
    """))
    self.add_to_build_file('resources/a', dedent("""
      resources(
        name='a_resources',
        sources=['a.resource']
      )
    """))
    self.add_to_build_file('src/java/a', dedent("""
      java_library(
        name='a_java',
        resources=[pants('resources/a:a_resources')]
      )
    """))
    self.add_to_build_file('src/java/a', dedent("""
      target(
        name='a_dep',
        dependencies=[pants(':a_java')]
      )
    """))

    self.add_to_build_file('src/java/b', dedent("""
      java_library(
        name='b_java',
        dependencies=[':b_dep']
      )
      target(
        name='b_dep',
        dependencies=[':b_lib']
      )
      java_library(
        name='b_lib',
        sources=[],
      )
    """))

    # It makes no sense whatsoever to have a java_library that depends
    # on a Python library, but we want to ensure that depmap handles
    # cases like this anyway because there might be other cases which
    # do make sense (e.g. things that generate generic resources)
    self.add_to_build_file('src/java/java_depends_on_python', dedent("""
      java_library(
        name='java_depends_on_python',
        dependencies=['common/d:d']
      )
    """))

  def test_java_depends_on_python(self):
    self.assert_console_output_ordered(
      'internal-src.java.java_depends_on_python.java_depends_on_python',
      '  internal-common.d.d',
      targets=[self.target('src/java/java_depends_on_python')]
    )

  def test_empty(self):
    self.assert_console_output_ordered(
      'internal-common.a.a',
      targets=[self.target('common/a')]
    )

  def test_jar_library(self):
    self.assert_console_output_ordered(
      'internal-common.b.b',
      targets=[self.target('common/b')],
    )

  def test_java_library(self):
    self.assert_console_output_ordered(
      'internal-common.c.c',
      targets=[self.target('common/c')]
    )

  def test_python_library(self):
    self.assert_console_output_ordered(
      'internal-common.d.d',
      targets=[self.target('common/d')]
    )

  def test_python_binary(self):
    self.assert_console_output_ordered(
      'internal-common.e.e',
      targets=[self.target('common/e')]
    )

  def test_jvm_binary1(self):
    self.assert_console_output_ordered(
      'internal-common.f.f',
      targets=[self.target('common/f')]
    )

  def test_jvm_binary2(self):
    self.assert_console_output_ordered(
      'internal-common.g.g',
      '  internal-common.f.f',
      targets=[self.target('common/g')]
    )

  def test_jvm_app1(self):
    self.assert_console_output_ordered(
      'internal-common.h.h',
      '  internal-common.f.f',
      targets=[self.target('common/h')]
    )

  def test_jvm_app2(self):
    self.assert_console_output_ordered(
      'internal-common.i.i',
      '  internal-common.g.g',
      '    internal-common.f.f',
      targets=[self.target('common/i')]
    )

  def test_overlaps_one(self):
    self.assert_console_output_ordered(
      'internal-overlaps.one',
      '  internal-common.h.h',
      '    internal-common.f.f',
      '  internal-common.i.i',
      '    internal-common.g.g',
      '      *internal-common.f.f',
      targets=[self.target('overlaps:one')]
    )

  def test_overlaps_two(self):
    self.assert_console_output_ordered(
      'internal-overlaps.two',
      '  internal-overlaps.one',
      '    internal-common.h.h',
      '      internal-common.f.f',
      '    internal-common.i.i',
      '      internal-common.g.g',
      '        *internal-common.f.f',
      targets=[self.target('overlaps:two')]
    )

  def test_overlaps_two_minimal(self):
    self.assert_console_output_ordered(
      'internal-overlaps.two',
      '  internal-overlaps.one',
      '    internal-common.h.h',
      '      internal-common.f.f',
      '    internal-common.i.i',
      '      internal-common.g.g',
      targets=[self.target('overlaps:two')],
      options={'minimal': True}
    )

  def test_multi(self):
    self.assert_console_output_ordered(
      'internal-common.g.g',
      '  internal-common.f.f',
      'internal-common.h.h',
      '  internal-common.f.f',
      'internal-common.i.i',
      '  internal-common.g.g',
      '    internal-common.f.f',
      targets=[self.target('common/g'), self.target('common/h'), self.target('common/i')]
    )

  def test_path_to(self):
    self.assert_console_output_ordered(
      'internal-overlaps.two',
      '  internal-overlaps.one',
      '    internal-common.i.i',
      '      internal-common.g.g',
      targets=[self.target('overlaps:two')],
      options={'path_to': 'internal-common.g.g'},
    )

  def test_resources(self):
    self.assert_console_output_ordered(
      'internal-src.java.a.a_java',
      '  internal-resources.a.a_resources',
      targets=[self.target('src/java/a:a_java')]
    )

  def test_resources_dep(self):
    self.assert_console_output_ordered(
      'internal-src.java.a.a_dep',
      '  internal-src.java.a.a_java',
      '    internal-resources.a.a_resources',
      targets=[self.target('src/java/a:a_dep')]
    )

  def test_intermediate_dep(self):
    self.assert_console_output_ordered(
      'internal-src.java.b.b_java',
      '  internal-src.java.b.b_dep',
      '    internal-src.java.b.b_lib',
      targets=[self.target('src/java/b:b_java')]
    )
