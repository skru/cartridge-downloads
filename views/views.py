import logging
import functools

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.shortcuts import redirect, render

from django_downloadview import ObjectDownloadView

from ..models import Acquisition, Download, Transaction
from ..utils import credential, session_downloads

# https://docs.djangoproject.com/en/stable/topics/logging/#django-request
logger = logging.getLogger('django.request')


def authenticate(request, id, token):
    credential(request, {'id': id, 'token': token})
    return redirect(index)


def _authenticate(func):
    """ View decorator that validates credentials and injects transaction. """
    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            with session_downloads(request) as session:
                _id = session['id']
                token = session['token']
        except KeyError:
            logger.warning('Cookie not found.', exc_info=True)
            raise PermissionDenied

        request.transaction = Transaction.objects.get(id=_id)

        if not request.transaction.check_token(token):
            raise PermissionDenied

        return func(request, *args, **kwargs)
    return wrapper


@_authenticate
def index(request):
    print(request,'>>>>>>>>>>>>>>>>>>>>>>>##########')
    acquisition_pages = set([
        acq.page for acq in
        Acquisition.objects.filter(
            transaction=request.transaction).select_subclasses()])

    return render(request,
                  'shop/downloads/index.html',
                  {'acquisition_pages': acquisition_pages})


class CartridgeDownloadView(ObjectDownloadView):
    def get(self, request, slug):
        # Look up acquisition.
        acquisition = Acquisition.objects.get(
            download__slug=slug, transaction=request.transaction)

        # Do nothing if the download limit has been reached.
        if acquisition.download_count >= acquisition.download_limit:
            messages.add_message(
                request,
                messages.ERROR,
                'Download Limit Exceeded. Please contact us for assistance.')
            return redirect(request.META.get('HTTP_REFERER', '/'))

        # Otherwise proceed with download.
        else:
            acquisition.download_count = F('download_count') + 1
            acquisition.save()

            return super(CartridgeDownloadView, self).get(self, request)

download = _authenticate(CartridgeDownloadView.as_view(model=Download))
