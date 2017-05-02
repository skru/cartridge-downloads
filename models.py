import uuid

from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.crypto import get_random_string

from mezzanine.conf import settings
from mezzanine.core.fields import FileField

from model_utils.managers import InheritanceManager
from django.utils.safestring import mark_safe
from django.core.files.storage import FileSystemStorage

private_media = FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT,
                                  base_url=settings.CARTRIDGE_DOWNLOADS_UPLOAD_DIR,
                                  )
from django.template.defaultfilters import slugify
import posixpath

# def upload_path_handler(instance, filename):
#     """
#     Splits the given filename into a dir structure and filename
#     eg NAME_YEAR_FILENAME = NAME/YEAR/FILENAME in the upload directory.
#     Camelcase/clean the filename and lowercases the file extension
#     """
#     #dirs = filename.split('_', 2)
#     fname, ext = dirs[2].split('.',-1)
#     name = ''.join(x for x in fname.title() if not x.isspace()) \
#         .replace('_', '')[:39] + '.' + ext.lower()
#     return "{}/{}/{}".format(dirs[0], dirs[1], name)

def upload_path_handler(instance, filename):
    """
    Splits the given filename into a dir structure and filename
    eg NAME_YEAR_FILENAME = NAME/YEAR/FILENAME in the upload directory.
    Camelcase/clean the filename and lowercases the file extension
    """
    #dirs = filename.split('_', 2)
    fname, ext = filename.split('.',-1)
    name = ''.join(x for x in fname.title() if not x.isspace()) \
        .replace('_', '')[:39] + '.' + ext.lower()
    return name

class Download(models.Model):
    file = models.FileField(storage=private_media,
        upload_to=upload_path_handler,
        help_text=mark_safe('''
            <br>
            <h3>FILENAMES MUST ADHERE TO NAMING CONSTRAINTS</h3>
            Please pre-name any files following the example:<br>
            eg: EventYearFileName.xxx
            <br>
            <span style='color:red;'>
            ALL FILES MUST FOLLOW THIS EXAMPLE
            </span>
            ''')
    )

    products = models.ManyToManyField('shop.Product', related_name='downloads')
    forms = models.ManyToManyField('forms.Form', related_name='downloads')

    slug = models.SlugField(unique=True, editable=False)

    def __str__(self):
        return self.file.name

    def clean(self):
        # On modification, do not allow filename to change.
        if self.slug and self.slug != self.file.name:
            raise ValidationError(
                'The filename "{f}" must remain the same.'.format(f=self.slug))

    def save(self, *args, **kwargs):
        # On initial save, set slug to friendly filename.
        self.slug = self.file.name if not self.slug else self.slug
        super(Download, self).save(*args, **kwargs)

    def validate_unique(self, *args, **kwargs):
        # Do not allow duplicate filenames.
        try:
            download = Download.objects.get(slug=self.file.name)
        except Download.DoesNotExist:
            pass
        else:
            # We're ok if we're changing the file but the filename is the same.
            if download != self:
                raise ValidationError(
                    'A download with that file name already exists.')

        super(Download, self).validate_unique(*args, **kwargs)


class Transaction(models.Model):
    # Use a uuid because these get exposed to users and we don't necessarily
    # want to reveal the transaction count to them.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    token_hash = models.CharField(max_length=128)

    def make_credentials(self):
        return {'id': self.id.hex, 'token': self.make_token()}

    def make_token(self):
        token = get_random_string()

        # We don't need a real salt because the attacks salts protect against
        # aren't applicable to random "passwords".
        self.token_hash = make_password(token, salt='fake_salt')

        return token

    def check_token(self, token):
        return check_password(token, self.token_hash)


class Acquisition(models.Model):
    download = models.ForeignKey(
        'Download', on_delete=models.PROTECT, null=True)
    download_count = models.IntegerField(default=0,
                                         editable=False,
                                         verbose_name='Download Count')
    download_limit = models.IntegerField(default=100,
                                         verbose_name='Download Limit')
    transaction = models.ForeignKey(
        Transaction, on_delete=models.PROTECT, null=True)

    objects = InheritanceManager()

    @property
    def page(self):
        """
        Return a related model which must have 'title' and 'downloads' fields.
        """
        raise NotImplementedError


class Purchase(Acquisition):
    order = models.ForeignKey(
        'shop.Order', on_delete=models.PROTECT, editable=False)
    product = models.ForeignKey(
        'shop.Product', on_delete=models.PROTECT, editable=False)

    @property
    def page(self):
        return self.product


class Promotion(Acquisition):
    formentry = models.ForeignKey(
        'forms.FormEntry', on_delete=models.PROTECT, editable=False)

    @property
    def page(self):
        return self.formentry.form
