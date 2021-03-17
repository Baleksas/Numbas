import zipfile
import os
from pathlib import Path
import json

from django.conf import settings
from django import forms
from django.forms.models import inlineformset_factory, modelformset_factory
from django.forms.widgets import SelectMultiple
from django.utils.html import format_html, html_safe
from django.utils.safestring import mark_safe
from django.utils.encoding import force_text
from django.db import transaction
from django.db.models import Q, Count
from django.contrib.auth.models import User
from django.template.loader import render_to_string

from editor.models import NewExam, NewQuestion, EditorItem, Access, Theme, Extension, \
    PullRequest, CustomPartType, Project, Folder, Resource, KnowledgeGraph, Topic, LearningObjective
import editor.models
from accounts.forms import UserField
from accounts.util import find_users
from editor import jsonfield

from .slugify import slugify
import json

class FixedSelectMultiple(SelectMultiple):
    def value_from_datadict(self, data, files, name):
        name += '[]'
        v = super(FixedSelectMultiple, self).value_from_datadict(data, files, name)
        return v

class TagField(forms.CharField):
    def clean(self, value):
        tags_string = super(TagField, self).clean(value)
        if len(tags_string.strip()):
            tags = tags_string.split(',')
            return [t.strip() for t in tags]
        else:
            return []

USAGE_OPTIONS = (
    ('any', 'Any'),
    ('reuse', 'Free to reuse'),
    ('modify', 'Free to reuse with modification'),
    ('sell', 'Free to reuse commercially'),
    ('modify-sell', 'Free to reuse commercially with modification'),
)

class BootstrapCheckboxInput(forms.CheckboxSelectMultiple):
    def build_attrs(self,base_attrs,extra_attrs):
        attrs = super(BootstrapCheckboxInput, self).build_attrs(base_attrs, extra_attrs)
        attrs['class'] = attrs.get('class','')+' list-unstyled'
        return attrs

class BootstrapRadioSelect(forms.RadioSelect):
    def build_attrs(self,base_attrs,extra_attrs):
        attrs = super(BootstrapRadioSelect, self).build_attrs(base_attrs, extra_attrs)
        attrs['class'] = attrs.get('class','')+' list-unstyled'
        return attrs

class BootstrapSelect(forms.Select):
    def build_attrs(self, base_attrs, extra_attrs):
        attrs = super(BootstrapSelect, self).build_attrs(base_attrs, extra_attrs)
        attrs['class'] = 'form-control input-sm'
        return attrs

class UserSearchMixin(forms.ModelForm):
    """
        Add a user_search field to the form, which resolves a string query to a User object, and set the property user_attr on the model to that user.
    """
    user_search = UserField(label='User')
    user_attr = 'user'
    selected_user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super(UserSearchMixin, self).__init__(*args, **kwargs)
        self.fields['user_search'] = UserField()

    def clean(self):
        cleaned_data = super(UserSearchMixin, self).clean()
        selected_user = cleaned_data.get('selected_user')
        if selected_user is not None:
            cleaned_data['user_search'] = selected_user

        if cleaned_data.get('user_search') is None:
            raise forms.ValidationError("No such user")

        return cleaned_data

    def save(self, commit=True, force_insert=False, force_update=False):
        m = super(UserSearchMixin, self).save(commit=False)
        setattr(m, self.user_attr, self.cleaned_data['user_search'])
        if commit:
            m.save()
        return m


class EditorItemSearchForm(forms.Form):
    query = forms.CharField(initial='', required=False)
    item_types = forms.MultipleChoiceField(initial=('questions', 'exams'), choices=(('questions', 'Questions'), ('exams', 'Exams')), widget=BootstrapCheckboxInput, required=False)
    author = forms.CharField(initial='', required=False, widget=forms.TextInput(attrs={'class':'form-control'}))
    usage = forms.ChoiceField(initial='any', choices=USAGE_OPTIONS, required=False, widget=BootstrapRadioSelect)
    taxonomy_nodes = forms.ModelMultipleChoiceField(queryset=editor.models.TaxonomyNode.objects.all(), required=False)
    ability_framework = forms.ModelChoiceField(queryset=editor.models.AbilityFramework.objects.all(), required=False, widget=forms.Select(attrs={'class':'form-control input-sm'}), empty_label=None)
    ability_levels = forms.ModelMultipleChoiceField(queryset=editor.models.AbilityLevel.objects.all(), widget=forms.CheckboxSelectMultiple, required=False)
    status = forms.ChoiceField(choices=[('any', 'Any status'),('draft','Draft')]+list(editor.models.STAMP_STATUS_CHOICES), required=False, widget=BootstrapRadioSelect)
    order_by = forms.ChoiceField(choices=[('last_modified', 'Last modified'), ('name', 'Name'), ('licence', 'Usage rights'), ('author', 'Author')], required=False, widget=BootstrapSelect, initial='last_modified')

    tags = TagField(initial='', required=False, widget=forms.TextInput(attrs={'placeholder': 'Tags separated by commas'}))
    exclude_tags = TagField(initial='', required=False, widget=forms.TextInput(attrs={'placeholder': 'Tags separated by commas'}))

class AccessForm(forms.ModelForm):
    given_by = forms.ModelChoiceField(queryset=User.objects.all())

    class Meta:
        model = Access
        exclude = []

    def save(self, commit=True):
        self.instance.given_by = self.cleaned_data.get('given_by')
        super(AccessForm, self).save(commit)

class SetAccessForm(forms.ModelForm):
    given_by = forms.ModelChoiceField(queryset=User.objects.all())

    class Meta:
        model = EditorItem
        fields = ['public_access']

    def is_valid(self):
        v = super(SetAccessForm, self).is_valid()
        for f in self.user_access_forms:
            if not f.is_valid():
                return False
        return v
    
    def clean(self):
        cleaned_data = super(SetAccessForm, self).clean()

        self.user_ids = self.data.getlist('user_ids[]')
        self.access_levels = self.data.getlist('access_levels[]')
        self.user_access_forms = []

        for i, (user, access_level) in enumerate(zip(self.user_ids, self.access_levels)):
            f = AccessForm({'user':user, 'access':access_level, 'item':self.instance.pk, 'given_by':self.cleaned_data.get('given_by').pk}, instance=Access.objects.filter(item=self.instance, user=user).first())
            f.full_clean()
            self.user_access_forms.append(f)
            for key, warnings in f.errors.items():
                self._errors[('user %i: ' % i)+key] = warnings

        return cleaned_data

    def save(self, commit=True):
        access_to_remove = Access.objects.filter(item=self.instance).exclude(user__in=self.user_ids)
        access_to_remove.delete()
        for f in self.user_access_forms:
            f.save()
        return super(SetAccessForm, self).save()
        
class EditorItemForm(forms.ModelForm):
    content = forms.CharField()

    taxonomy_nodes = forms.ModelMultipleChoiceField(queryset=editor.models.TaxonomyNode.objects.all(), required=False)
    ability_levels = forms.ModelMultipleChoiceField(queryset=editor.models.AbilityLevel.objects.all(), required=False)

    def save(self, commit=True):
        obj = super(EditorItemForm, self).save(commit=commit)
        obj.editoritem.content = self.cleaned_data['content']
        obj.editoritem.save()
        return obj

class CopyEditorItemForm(forms.ModelForm):
    class Meta:
        model = EditorItem
        fields = ('name', 'project')
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control', 'placeholder':'e.g. "Solve an equation in two variables"'}),
            'project': BootstrapSelect,
        }

class EditorItemMoveProjectForm(forms.ModelForm):
    class Meta:
        model = EditorItem
        fields = ('project',)
        widgets = {
            'project': BootstrapSelect,
        }

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.folder = None
        if commit:
            obj.save()
        return obj
    
class QuestionForm(EditorItemForm):
    
    class Meta:
        model = NewQuestion
        fields = ('resources', 'extensions')

class NewQuestionForm(forms.ModelForm):

    parts_mode = forms.ChoiceField(choices=(('all','Show all parts'),('explore','Explore')),widget=BootstrapSelect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['folder'].required = False

    def clean(self):
        cleaned_data = super().clean()
        project = cleaned_data.get('project')
        folder = cleaned_data.get('folder')
        if folder and folder.project != project:
            raise forms.ValidationError("Folder {} isn't in the project {}".format(folder,project))
        return cleaned_data

    class Meta:
        model = EditorItem
        fields = ('name', 'author', 'project', 'folder')
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control', 'placeholder':'e.g. "Solve an equation in two variables"'}),
            'author': forms.HiddenInput(),
            'folder': forms.HiddenInput(),
            'project': BootstrapSelect,
        }

ResourcesAltTextForm = modelformset_factory(Resource, fields=('alt_text',))

class ExamForm(EditorItemForm):
    class Meta:
        model = NewExam
        fields = ('theme', 'custom_theme', 'locale')
        
class NewExamForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['folder'].required = False

    def clean(self):
        cleaned_data = super().clean()
        project = cleaned_data.get('project')
        folder = cleaned_data.get('folder')
        if folder and folder.project != project:
            raise forms.ValidationError("Folder {} isn't in the project {}".format(folder,project))
        return cleaned_data

    class Meta:
        model = EditorItem
        fields = ('name', 'author', 'project', 'folder')
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control', 'placeholder':'e.g. "Week 4 homework"'}),
            'author': forms.HiddenInput(),
            'folder': forms.HiddenInput(),
            'project': BootstrapSelect,
        }

def validate_exam_file(f):
    try:
        content = f.read().decode('utf-8')
        editor.models.validate_content(content)
        f.seek(0)
    except (UnicodeDecodeError, forms.ValidationError):
        raise forms.ValidationError("Not a valid .exam file")

class UploadExamForm(forms.ModelForm):
    file = forms.FileField(required=True, validators=[validate_exam_file])

    class Meta:
        model = EditorItem
        fields = ('file', 'project',)
        widgets = {
            'author': forms.HiddenInput(),
            'project': BootstrapSelect,
        }

class ValidateZipField:
    def clean_zipfile(self):
        value = self.cleaned_data['zipfile']
        if not zipfile.is_zipfile(value):
            raise forms.ValidationError('Uploaded file is not a zip file')
        return value


class EditPackageForm(forms.ModelForm):
    
    """Form to edit a file in a package."""

    source = forms.CharField(widget=forms.Textarea,required=False)
    filename = forms.CharField(widget=forms.HiddenInput)
    
    class Meta:
        fields = []

    def save(self, commit=True):
        package = super().save(commit=False)
        filename = self.cleaned_data.get('filename')
        if commit:
            path = os.path.join(package.extracted_path,filename)
            Path(path).parent.mkdir(parents=True,exist_ok=True)
            with open(path,'w',encoding='utf-8') as f:
                f.write(self.cleaned_data.get('source'))
        return package

class EditPackageReplaceFileForm(forms.ModelForm):
    
    """Form to replace a file in a package."""

    content = forms.FileField()
    filename = forms.CharField(widget=forms.HiddenInput,required=False)
    
    class Meta:
        fields = []

    def save(self, commit=True):
        package = super().save(commit=False)
        filename = self.cleaned_data.get('filename')
        if commit:
            nf = self.cleaned_data.get('content')
            if not filename:
                filename = nf.name
            path = os.path.join(package.extracted_path,filename)
            Path(path).parent.mkdir(parents=True,exist_ok=True)
            with open(path,'wb') as f:
                f.write(nf.read())
        return package

class EditExtensionForm(EditPackageForm):
    class Meta(EditPackageForm.Meta):
        model = Extension

class ReplaceExtensionFileForm(EditPackageReplaceFileForm):
    class Meta(EditPackageReplaceFileForm.Meta):
        model = Extension

class PackageDeleteFileForm(forms.ModelForm):
    filename = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        fields = []

    def save(self, commit=True):
        package = super().save(commit=False)
        filename = self.cleaned_data.get('filename')
        if commit:
            path = os.path.join(package.extracted_path,filename)
            os.remove(path)
        return package

class ExtensionDeleteFileForm(PackageDeleteFileForm):
    class Meta(PackageDeleteFileForm.Meta):
        model = Extension

class UpdateExtensionForm(forms.ModelForm):
    
    """Form to edit an extension."""
    
    class Meta:
        model = Extension
        fields = ['name', 'location', 'url', 'zipfile']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'location': forms.TextInput(attrs={'class':'form-control'}),
            'url': forms.TextInput(attrs={'class':'form-control'}),
            'zipfile': forms.FileInput()
        }

    def clean_zipfile(self):
        file = self.cleaned_data['zipfile']
        if file is None:
            return
        if not zipfile.is_zipfile(file):
            _, extension = os.path.splitext(file.name)
            if extension.lower() == '.js':
                return file
            else:
                raise forms.ValidationError('Uploaded file is not a .zip file or .js file.')
        else:
            return file

    def clean_location(self):
        location = self.cleaned_data.get('location')
        if location == '':
            raise forms.ValidationError('You must give a short name.')

        return location

class CreateExtensionForm(forms.ModelForm):
    
    """Form for a new extension."""

    class Meta:
        model = Extension
        fields = ['name']
    
    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('author')
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get('name')
        location = slugify(name)
        if Extension.objects.filter(location=location).exists():
            raise forms.ValidationError("An extension with that name already exists.")
        return name

    def save(self, commit=True):
        extension = super().save(commit=False)
        extension.location = slugify(extension.name)
        extension.public = False
        extension.author = self._user
        if commit:
            extension.save()
            self.save_m2m()
            extension.ensure_extracted_path_exists()
            extension.write_file(extension.main_filename,\
"""Numbas.addExtension('{location}',['jme'],function(extension) {{
  var scope = extension.scope;

  // write your extension code here
}});""".format(location=extension.location))
            extension.write_file('README.md',\
"""# {name}

The author of this extension should write some documentation about how it works.""".format(name=extension.name))
        return extension

class UploadExtensionForm(UpdateExtensionForm):
    
    """Form to upload an extension."""
    
    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('author')
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        extension = super().save(commit=False)
        extension.public = False
        extension.author = self._user
        if commit:
            extension.save()
            self.save_m2m()
        return extension

ExtensionAccessFormset = inlineformset_factory(editor.models.Extension, editor.models.ExtensionAccess, fields=('access',), extra=0, can_delete=True)

class AddExtensionAccessForm(UserSearchMixin, forms.ModelForm):
    invitation = None
    adding_user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput())

    class Meta:
        model = editor.models.ExtensionAccess
        fields = ('extension', 'access')
        widgets = {
            'extension': forms.HiddenInput(),
            'access': forms.Select(attrs={'class':'form-control'})
        }

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('user_search')
        if user == cleaned_data.get('extension').author:
            raise forms.ValidationError("Can't give separate access to the extension's author")
        return cleaned_data

    def save(self, force_insert=False, force_update=False, commit=True):
        m = super().save(commit=False)
        if commit:
            if m.user.pk:
                # check if there's an existing ExtensionAccess for this user & project
                ea = editor.models.ExtensionAccess.objects.filter(extension=m.extension, user=m.user).first()
                if ea is not None:
                    ea.access = m.access
                    m = ea
                m.save()
        return m

class EditThemeForm(EditPackageForm):
    class Meta(EditPackageForm.Meta):
        model = Theme

class ReplaceThemeFileForm(EditPackageReplaceFileForm):
    class Meta(EditPackageReplaceFileForm.Meta):
        model = Theme

class ThemeDeleteFileForm(PackageDeleteFileForm):
    class Meta(PackageDeleteFileForm.Meta):
        model = Theme

ThemeAccessFormset = inlineformset_factory(editor.models.Theme, editor.models.ThemeAccess, fields=('access',), extra=0, can_delete=True)

class AddThemeAccessForm(UserSearchMixin, forms.ModelForm):
    invitation = None
    adding_user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput())

    class Meta:
        model = editor.models.ThemeAccess
        fields = ('theme', 'access')
        widgets = {
            'theme': forms.HiddenInput(),
            'access': forms.Select(attrs={'class':'form-control'})
        }

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('user_search')
        if user == cleaned_data.get('theme').author:
            raise forms.ValidationError("Can't give separate access to the theme's author")
        return cleaned_data

    def save(self, force_insert=False, force_update=False, commit=True):
        m = super().save(commit=False)
        if commit:
            if m.user.pk:
                # check if there's an existing ThemeAccess for this user & project
                ea = editor.models.ThemeAccess.objects.filter(theme=m.theme, user=m.user).first()
                if ea is not None:
                    ea.access = m.access
                    m = ea
                m.save()
        return m

class UpdateThemeForm(forms.ModelForm, ValidateZipField):
    
    """Form to edit a theme."""
    
    class Meta:
        model = Theme
        fields = ['name', 'zipfile']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'zipfile': forms.FileInput()
        }
 
THEME_INIT_FILES = {
    'README.md': 'README.md',
    'files/resources/styles.css': 'style.css',
    'inherit.txt': 'inherit.txt',
}

class CreateThemeForm(forms.ModelForm):
    
    """Form for a new theme."""

    class Meta:
        model = Theme
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('author')
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        theme = super().save(commit=False)
        theme.public = False
        theme.author = self._user
        if commit:
            theme.save()
            self.save_m2m()
            theme.ensure_extracted_path_exists()
            for fname,tname in THEME_INIT_FILES.items():
                content = render_to_string('theme/init-files/'+tname, {'name': theme.name})
                theme.write_file(fname,content)
        return theme

class UploadThemeForm(UpdateThemeForm):
    
    """Form to upload a theme."""
    
    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('author')
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        theme = super().save(commit=False)
        theme.public = False
        theme.author = self._user
        if commit:
            theme.save()
            self.save_m2m()
        return theme

class UpdateCustomPartTypeForm(forms.ModelForm):
    
    """Form to edit a custom part type."""
    
    class Meta:
        model = CustomPartType
        fields = ['name', 'short_name', 'description', 'help_url', 'input_widget', 'input_options', 'can_be_gap', 'can_be_step', 'settings', 'marking_script', 'marking_notes', 'ready_to_use', 'extensions']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'short_name': forms.TextInput(attrs={'class':'form-control'}),
            'input_widget': forms.widgets.Select(choices=editor.models.CUSTOM_PART_TYPE_INPUT_WIDGETS, attrs={'class':'form-control'}),
            'settings': jsonfield.JSONWidget(),
            'input_options': jsonfield.JSONWidget(),
        }

    def clean_short_name(self):
        short_name = self.cleaned_data.get('short_name')
        built_in_part_types = ['jme','numberentry','patternmatch','matrix','gapfill','information','extension','1_n_2','m_n_2','m_n_x']
        if short_name in built_in_part_types:
            raise forms.ValidationError("The unique identifier you chose is already in use.")
        return short_name

    def clean_marking_script(self):
        marking_script = self.cleaned_data.get('marking_script')
        return marking_script.replace('\r','')

class NewCustomPartTypeForm(forms.ModelForm):
    
    """Form for a new custom part type."""

    class Meta:
        model = CustomPartType
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('author')
        super(NewCustomPartTypeForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        custom_part_type = super(NewCustomPartTypeForm, self).save(commit=False)

        slug = slugify(custom_part_type.name)
        custom_part_type.set_short_name(slug)
        
        custom_part_type.author = self._user

        if commit:
            custom_part_type.save()
            self.save_m2m()
        return custom_part_type

def validate_custom_part_type_json_file(f):
    try:
        content = f.read().decode('utf-8')
        data = json.loads(content)
        f.seek(0)
    except (UnicodeDecodeError, json.JSONDecodeError, forms.ValidationError):
        raise forms.ValidationError("Not a valid custom part type definition file")

class UploadCustomPartTypeForm(forms.ModelForm):
    file = forms.FileField(required=True, validators=[validate_custom_part_type_json_file])

    class Meta:
        model = CustomPartType
        fields = ['author']
        widgets = {
            'author': forms.HiddenInput(),
        }

    def clean_file(self):
        json_file = self.cleaned_data.get('file')
        content = json_file.read().decode('utf-8')
        data = json.loads(content)
        self.cleaned_data['json'] = data
        return content

    def save(self, commit=True):
        data = self.cleaned_data.get('json')
        extensions = data.get('extensions',[])
        del data['extensions']
        kwargs = {}
        for key in ['name','short_name','description','input_widget','input_options','can_be_gap','can_be_step','marking_script','marking_notes','settings','help_url','ready_to_use']:
            if key in data:
                kwargs[key] = data[key]
        cpt = CustomPartType(author=self.cleaned_data.get('author'), **kwargs)
        if(commit):
            cpt.save()
            cpt.extensions.set(Extension.objects.filter(location__in=extensions))
        return cpt

class CopyCustomPartTypeForm(forms.ModelForm):
    class Meta:
        model = CustomPartType
        fields = ('name',)
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name == self.instance.name:
            raise forms.ValidationError("Please pick a new name.")
        return name

class AddMemberForm(UserSearchMixin, forms.ModelForm):
    invitation = None
    adding_user = forms.ModelChoiceField(queryset=User.objects.all(), widget=forms.HiddenInput())

    class Meta:
        model = editor.models.ProjectAccess
        fields = ('project', 'access')
        widgets = {
            'project': forms.HiddenInput(),
            'access': forms.Select(attrs={'class':'form-control'})
        }

    def clean(self):
        cleaned_data = super(AddMemberForm, self).clean()
        user = cleaned_data.get('user_search')
        if user == cleaned_data.get('project').owner:
            raise forms.ValidationError("Can't give separate access to the project owner")
        if not user.pk:
            if not settings.ALLOW_REGISTRATION:
                raise forms.ValidationError("Self-registration is disabled, so you can't invite a user by email address.")
        return cleaned_data

    def save(self, force_insert=False, force_update=False, commit=True):
        m = super(AddMemberForm, self).save(commit=False)
        if commit:
            if m.user.pk:
                # check if there's an existing ProjectAccess for this user & project
                pa = editor.models.ProjectAccess.objects.filter(project=m.project, user=m.user).first()
                if pa is not None:
                    pa.access = m.access
                    m = pa
                m.save()
            else:   # create email invitation if the user_search field contained an email address
                self.invitation = editor.models.ProjectInvitation.objects.create(invited_by=self.cleaned_data.get('adding_user'), project=m.project, access=m.access, email=m.user.email)
        return m

class ProjectForm(forms.ModelForm):
    class Meta:
        model = editor.models.Project
        fields = ('name', 'description', 'default_licence', 'default_locale', 'public_view')
        widgets = {
            'default_locale': forms.widgets.Select(choices=editor.models.LOCALE_CHOICES, attrs={'class':'form-control'})
        }

class ProjectTransferOwnershipForm(UserSearchMixin, forms.ModelForm):
    user_attr = 'owner'
    class Meta:
        model = editor.models.Project 
        fields = []

class EditorItemTransferOwnershipForm(UserSearchMixin, forms.ModelForm):
    user_attr = 'author'
    class Meta:
        model = editor.models.EditorItem
        fields = []

ProjectAccessFormset = inlineformset_factory(editor.models.Project, editor.models.ProjectAccess, fields=('access',), extra=0)
ProjectInvitationFormset = inlineformset_factory(editor.models.Project, editor.models.ProjectInvitation, fields=('access',), extra=0)

class NewFolderForm(forms.ModelForm):
    parent = forms.ModelChoiceField(queryset=editor.models.Folder.objects.all(), required=False, widget=forms.HiddenInput())

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if '/' in name:
            raise forms.ValidationError("Folder names may not include a forward slash.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        name = self.cleaned_data.get('name')
        project = self.cleaned_data.get('project')
        parent = self.cleaned_data.get('parent')
        if project.folders.filter(name=name,parent=parent).exists():
            raise forms.ValidationError("A folder with that name already exists.")
        return cleaned_data

    class Meta:
        model = editor.models.Folder
        fields = ['name','project','parent']
        widgets = {
            'project': forms.HiddenInput(),
        }

class MoveFolderForm(forms.ModelForm):
    project = forms.ModelChoiceField(queryset=editor.models.Project.objects.all(), required=False)
    parent = forms.ModelChoiceField(queryset=editor.models.Folder.objects.all(), required=False)
    folders = forms.ModelMultipleChoiceField(queryset=editor.models.Folder.objects.all(), required=False)
    items = forms.ModelMultipleChoiceField(queryset=editor.models.EditorItem.objects.all(), required=False)

    def clean(self):
        cleaned_data = super().clean()
        parent = cleaned_data.get('parent')
        parents = []
        if parent:
            parents.append(parent)
            f = parent.parent
            while f:
                parents.append(f)
                f = f.parent
        folders = cleaned_data.get('folders')
        items = cleaned_data.get('items')
        move_folders = []
        for folder in folders:
            if parent is not None and folder.project != parent.project:
                raise forms.ValidationError("Can't move a folder into a different project.")
            if folder not in parents:
                move_folders.append(folder)
        cleaned_data['folders'] = move_folders
        for item in items:
            if parent is not None and item.project != parent.project:
                raise forms.ValidationError("Can't move an item into a different project.")
            item.parent = parent
        return cleaned_data

    def save(self):
        parent = self.cleaned_data.get('parent')
        folders = self.cleaned_data.get('folders')
        items = self.cleaned_data.get('items')
        with transaction.atomic():
            for folder in folders:
                folder.parent = parent
                folder.save()
            for item in items:
                item.folder = parent
                item.save()

    class Meta:
        model = editor.models.EditorItem
        fields = ('parent',)

class BrowseMoveProjectForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.all(), required=True)
    items = forms.ModelMultipleChoiceField(queryset=EditorItem.objects.all(), required=False, widget=forms.MultipleHiddenInput())
    folders = forms.ModelMultipleChoiceField(queryset=Folder.objects.all(), required=False, widget=forms.MultipleHiddenInput())

    class Meta:
        widgets = {
            'items': forms.HiddenInput(),
            'folders': forms.HiddenInput(),
        }

    def save(self):
        project = self.cleaned_data.get('project')

        folders = []
        items = []

        with transaction.atomic():
            top_items = self.cleaned_data.get('items')
            for i in top_items:
                i.folder = None
            items += top_items

            for f in self.cleaned_data.get('folders'):
                f.parent = None
                subfolders,subitems = f.all_contents()
                folders += subfolders
                items += subitems

            for i in items:
                i.project = project
                i.save()
            for f in folders:
                f.project = project
                f.save()


class RenameFolderForm(forms.ModelForm):
    class Meta:
        model = editor.models.Folder
        fields = ('name',)

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if '/' in name:
            raise forms.ValidationError("Folder names may not include a forward slash.")
        if self.instance.project.folders.filter(name=name,parent=self.instance.parent).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A folder with this name already exists.")
        return name

class CreatePullRequestForm(forms.ModelForm):
    class Meta:
        model = PullRequest
        fields = ('source', 'destination', 'comment')

class CreateExamFromBasketForm(forms.ModelForm):
    clear_basket = forms.BooleanField(initial=True, label='Empty your basket after creation?', required=False)
    class Meta:
        model = EditorItem
        fields = ('name', 'author', 'project')
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control', 'placeholder':'e.g. "Week 4 homework"'}),
            'author': forms.HiddenInput(),
            'project': BootstrapSelect,
        }

class NewKnowledgeGraphForm(forms.ModelForm):
    
    """Form for a new knowledge graph."""

    class Meta:
        model = KnowledgeGraph
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self._user = kwargs.pop('author')
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        knowledge_graph = super().save(commit=False)

        knowledge_graph.slug = slugify(knowledge_graph.name)
        
        knowledge_graph.author = self._user

        if commit:
            knowledge_graph.save()
            self.save_m2m()
        return knowledge_graph


class UpdateKnowledgeGraphForm(forms.ModelForm):
    
    """Form to edit a knowledge graph."""

    data = forms.CharField(initial='',required=True)
    
    class Meta:
        model = KnowledgeGraph
        fields = ['name','description']

    def clean_data(self):
        value = self.cleaned_data['data']
        try:
            data = json.loads(value)
        except json.JSONDecodeError as e:
            raise forms.ValidationError("Invalid JSON data")
        return data

    def save(self, commit=True):
        knowledge_graph = self.object = super().save(commit=commit)

        if commit:
            with transaction.atomic():
                self.save_graph()

        return knowledge_graph

    def save_graph(self):
        data = self.cleaned_data['data']
        knowledge_graph = self.object

        topic_pks = [t.get('pk') for t in data.get('topics',[])]
        topics = list(Topic.objects.filter(pk__in=topic_pks))
        learning_objective_pks = [lo.get('pk') for lo in data.get('learning_objectives',[])]
        learning_objectives = list(LearningObjective.objects.filter(pk__in=learning_objective_pks))

        deleted_topics = Topic.objects.filter(knowledge_graph=knowledge_graph).exclude(pk__in=topic_pks)
        deleted_topics.delete()
        deleted_learning_objectives = LearningObjective.objects.filter(knowledge_graph=knowledge_graph).exclude(pk__in=learning_objective_pks)
        deleted_learning_objectives.delete()

        for t in data.get('topics',[]):
            if t.get('pk') is None:
                t = Topic.objects.create(knowledge_graph=knowledge_graph, name=t['name'], description=t['description'])
                topics.append(t)

        for lo in data.get('learning_objectives',[]):
            if lo.get('pk') is None:
                lo = LearningObjective.objects.create(knowledge_graph=knowledge_graph, name=lo['name'], description=lo['description'])
                learning_objectives.append(lo)

        topic_pks = {t.pk : t for t in topics if t.pk is not None}
        topic_names = {t.name : t for t in topics}
        learning_objective_pks = {lo.pk : lo for lo in learning_objectives if lo.pk is not None}
        learning_objective_names = {lo.name : lo for lo in learning_objectives}
        def get_topic(info):
            return topic_pks.get(info.get('pk'), topic_names.get(info['name']))
        def get_learning_objective(info):
            return learning_objective_pks.get(info.get('pk'), learning_objective_names.get(info['name']))

        for td in data.get('topics',[]):
            t = get_topic(td)
            t.name = td['name']
            t.description = td['description']
            t.depends_on.set([get_topic(info) for info in td['depends_on']])
            t.learning_objectives.set([get_learning_objective(info) for info in td['learning_objectives']])
            t.save()

        for lod in data.get('learning_objectives',[]):
            lo = get_learning_objective(lod)
            lo.name = lod['name']
            lo.description = lod['description']
            lo.save()

        self.topics = topics
        self.learning_objectives = learning_objectives
