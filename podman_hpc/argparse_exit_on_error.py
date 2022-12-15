from argparse import *
from argparse import ArgumentParser as _ArgumentParser

class ArgumentParser(_ArgumentParser):
    def __init__(self, *args, exit_on_error=True, **kwargs):
        self._exit_on_error=exit_on_error
        super().__init__(self,*args,**kwargs)

    def error(self,*args,**kwargs):
        if self._exit_on_error:
            super().error(self,*args,**kwargs)

