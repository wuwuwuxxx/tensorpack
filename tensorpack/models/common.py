# -*- coding: UTF-8 -*-
# File: common.py
# Author: Yuxin Wu <ppwwyyxx@gmail.com>

import tensorflow as tf
from functools import wraps
import six
import re
import copy

from ..tfutils.argscope import get_arg_scope
from ..tfutils.model_utils import get_shape_str
from ..utils import logger

# make sure each layer is only logged once
_LAYER_LOGGED = set()
_LAYER_REGISTERED = {}

__all__ = ['layer_register']


class VariableHolder(object):
    """ A proxy to access variables defined in a layer. """
    def __init__(self, **kwargs):
        """
        Args:
            kwargs: {name:variable}
        """
        self._vars = {}
        for k, v in six.iteritems(kwargs):
            self._add_variable(k, v)

    def _add_variable(self, name, var):
        assert name not in self._vars
        self._vars[name] = var

    def __setattr__(self, name, var):
        if not name.startswith('_'):
            self._add_variable(name, var)
        else:
            # private attributes
            super(VariableHolder, self).__setattr__(name, var)

    def __getattr__(self, name):
        return self._vars[name]

    def all(self):
        """
        Returns:
            list of all variables
        """
        return list(six.itervalues(self._vars))


def _register(name, func):
    if name in _LAYER_REGISTERED:
        raise ValueError("Layer named {} is already registered!".format(name))
    if name in ['tf']:
        raise ValueError(logger.error("A layer cannot be named {}".format(name)))
    _LAYER_REGISTERED[name] = func


def get_registered_layer(name):
    """
    Args:
        name (str): the name of the layer, e.g. 'Conv2D'
    Returns:
        the wrapped layer function, or None if not registered.
    """
    return _LAYER_REGISTERED.get(name, None)


def disable_layer_logging():
    """
    Disable the shape logging for all layers from this moment on. Can be
    useful when creating multiple towers.
    """
    class ContainEverything:
        def __contains__(self, x):
            return True
    # can use nonlocal in python3, but how
    globals()['_LAYER_LOGGED'] = ContainEverything()


def layer_register(
        log_shape=True,
        use_scope=True):
    """
    Register a layer.

    Args:
        log_shape (bool): log input/output shape of this layer
        use_scope (bool): whether to call this layer with an extra first argument as scope.
            If set to False, will try to figure out whether the first argument
            is scope name or not.
    """

    def wrapper(func):
        @wraps(func)
        def wrapped_func(*args, **kwargs):
            assert args[0] is not None, args
            if use_scope:
                name, inputs = args[0], args[1]
                args = args[1:]  # actual positional args used to call func
                assert isinstance(name, six.string_types), name
            else:
                assert not log_shape
                if isinstance(args[0], six.string_types):
                    name, inputs = args[0], args[1]
                    args = args[1:]  # actual positional args used to call func
                else:
                    inputs = args[0]
                    name = None
            if not (isinstance(inputs, (tf.Tensor, tf.Variable)) or
                    (isinstance(inputs, (list, tuple)) and
                        isinstance(inputs[0], (tf.Tensor, tf.Variable)))):
                raise ValueError("Invalid inputs to layer: " + str(inputs))

            # TODO use inspect.getcallargs to enhance?
            # update from current argument scope
            actual_args = copy.copy(get_arg_scope()[func.__name__])
            actual_args.update(kwargs)

            if name is not None:        # use scope
                with tf.variable_scope(name) as scope:
                    scope_name = re.sub('tower[0-9]+/', '', scope.name)
                    do_log_shape = log_shape and scope_name not in _LAYER_LOGGED
                    if do_log_shape:
                        logger.info("{} input: {}".format(scope.name, get_shape_str(inputs)))

                    # run the actual function
                    outputs = func(*args, **actual_args)

                    if do_log_shape:
                        # log shape info and add activation
                        logger.info("{} output: {}".format(
                            scope.name, get_shape_str(outputs)))
                        _LAYER_LOGGED.add(scope_name)
            else:
                # run the actual function
                outputs = func(*args, **actual_args)
            return outputs

        wrapped_func.symbolic_function = func   # attribute to access the underlying function object
        wrapped_func.use_scope = use_scope
        _register(func.__name__, wrapped_func)
        return wrapped_func

    return wrapper
