# coding=utf-8
# Copyright 2014 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import (absolute_import, division, generators, nested_scopes, print_function,
                        unicode_literals, with_statement)

from pants.backend.core.targets.resources import Resources
from pants.backend.jvm.targets.exclude import Exclude
from pants.backend.jvm.targets.jar_library import JarLibrary
from pants.backend.jvm.targets.jarable import Jarable
from pants.base.payload import Payload
from pants.base.payload_field import ConfigurationsField, ExcludesField
from pants.base.target import Target
from pants.util.memo import memoized_property


class JvmTarget(Target, Jarable):
  """A base class for all java module targets that provides path and dependency translation."""

  def __init__(self,
               address=None,
               payload=None,
               sources_rel_path=None,
               sources=None,
               provides=None,
               excludes=None,
               resources=None,
               configurations=None,
               no_cache=False,
               services=None,
               **kwargs):
    """
    :param configurations: One or more ivy configurations to resolve for this target.
      This parameter is not intended for general use.
    :type configurations: tuple of strings
    :param excludes: List of `exclude <#exclude>`_\s to filter this target's
      transitive dependencies against.
    :param sources: Source code files to build. Paths are relative to the BUILD
       file's directory.
    :type sources: ``Fileset`` (from globs or rglobs) or list of strings
    :param no_cache: If True, this should not be stored in the artifact cache
    :param services: A dict mapping service interface names to the classes owned by this target
                     that implement them.  Keys are fully qualified service class names, values are
                     lists of strings, each string the fully qualified class name of a class owned
                     by this target that implements the service interface and should be
                     discoverable by the jvm service provider discovery mechanism described here:
                     https://docs.oracle.com/javase/6/docs/api/java/util/ServiceLoader.html
    """
    self.address = address  # Set in case a TargetDefinitionException is thrown early
    if sources_rel_path is None:
      sources_rel_path = address.spec_path
    payload = payload or Payload()
    payload.add_fields({
      'sources': self.create_sources_field(sources, sources_rel_path, address),
      'provides': provides,
      'excludes': ExcludesField(self.assert_list(excludes, expected_type=Exclude, field_name='excludes')),
      'configurations': ConfigurationsField(self.assert_list(configurations, field_name='configurations')),
    })
    self._resource_specs = self.assert_list(resources, field_name='resources')

    super(JvmTarget, self).__init__(address=address, payload=payload,
                                    **kwargs)

    # Service info is only used when generating resources, it should not affect, for example, a
    # compile fingerprint or javadoc fingerprint.  As such, its not a payload field.
    self._services = services or {}

    self.add_labels('jvm')
    if no_cache:
      self.add_labels('no_cache')

  @memoized_property
  def jar_dependencies(self):
    return set(self.get_jar_dependencies())

  def mark_extra_invalidation_hash_dirty(self):
    del self.jar_dependencies

  def get_jar_dependencies(self):
    jar_deps = set()
    def collect_jar_deps(target):
      if isinstance(target, JarLibrary):
        jar_deps.update(target.payload.jars)

    self.walk(work=collect_jar_deps)
    return jar_deps

  @property
  def has_resources(self):
    return len(self.resources) > 0

  @property
  def traversable_dependency_specs(self):
    for spec in super(JvmTarget, self).traversable_dependency_specs:
      yield spec
    for resource_spec in self._resource_specs:
      yield resource_spec

  @property
  def provides(self):
    return self.payload.provides

  @property
  def resources(self):
    # TODO(John Sirois): Consider removing this convenience:
    #   https://github.com/pantsbuild/pants/issues/346
    # TODO(John Sirois): Introduce a label and replace the type test?
    return [dependency for dependency in self.dependencies if isinstance(dependency, Resources)]

  @property
  def excludes(self):
    return self.payload.excludes

  @property
  def services(self):
    return self._services
