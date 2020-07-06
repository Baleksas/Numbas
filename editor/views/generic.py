import json

from django.shortcuts import redirect
from django import http
from django.views import generic
from django.template.loader import get_template
from django.template import RequestContext
from django.template.response import TemplateResponse
import reversion

from editor.models import NewStampOfApproval, Comment, RestorePoint, EditorItem, Access

from accounts.util import user_json

def forbidden_response(request,message=None):
    return TemplateResponse(
        request=request,
        context={'message':message},
        template='403.html',
        status=403
    )

# from http://stackoverflow.com/questions/18172102/object-ownership-validation-in-django-updateview
class AuthorRequiredMixin(object):
    def dispatch(self, request, *args, **kwargs):
        if self.get_object().author != self.request.user:
            template = get_template("403.html")
            return http.HttpResponseForbidden(template.render(RequestContext(self.request).flatten()))
        result = super(AuthorRequiredMixin, self).dispatch(request, *args, **kwargs)
        return result

class CanEditMixin(object):
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if not obj.can_be_edited_by(request.user):
            template = get_template("403.html")
            return http.HttpResponseForbidden(template.render(RequestContext(self.request).flatten()))
        return super().dispatch(request, *args, **kwargs)

class CanViewMixin(object):
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if not obj.can_be_viewed_by(request.user):
            template = get_template("403.html")
            return http.HttpResponseForbidden(template.render(RequestContext(self.request).flatten()))
        return super().dispatch(request, *args, **kwargs)

class TimelineItemViewMixin(object):
    def response(self):
        data = {
            'object_json': self.object_json(),
            'html': self.object_html(),
        }
        return http.HttpResponse(json.dumps(data), content_type='application/json')

    def object_html(self):
        template = get_template(self.item.timelineitem_template)
        html = template.render(RequestContext(self.request, {'item': self.item.timelineitem, 'can_delete': self.item.can_be_deleted_by(self.request.user)}).flatten())
        return html

class StampView(generic.UpdateView, TimelineItemViewMixin):
    def post(self, request, *args, **kwargs):
        obj = self.get_object()

        status = request.POST.get('status')

        self.item = NewStampOfApproval.objects.create(user=request.user, object=obj.editoritem, status=status)

        return self.response()

    def object_json(self):
        return stamp_json(self.item)

    def get(self, request, *args, **kwargs):
        return http.HttpResponseNotAllowed(['POST'], 'GET requests are not allowed at this URL.')

class CommentView(generic.UpdateView, TimelineItemViewMixin):
    def post(self, request, *args, **kwargs):
        obj = self.get_comment_object()

        text = request.POST.get('text')

        self.item = Comment.objects.create(user=request.user, object=obj, text=text)

        return self.response()

    def object_json(self):
        return comment_json(self.item)

    def get(self, request, *args, **kwargs):
        return http.HttpResponseNotAllowed(['POST'], 'GET requests are not allowed at this URL.')

class SetRestorePointView(generic.UpdateView, TimelineItemViewMixin):
    def post(self, request, *args, **kwargs):
        obj = self.get_object()
    
        description = request.POST.get('text')
        if not reversion.models.Version.objects.get_for_object(obj).exists():
            with reversion.create_revision():
                obj.save()
                reversion.set_user(request.user)
        revision = reversion.models.Version.objects.get_for_object(obj).first().revision

        self.item = RestorePoint.objects.create(user=request.user, object=obj.editoritem, description=description, revision=revision)

        return self.response()

    def object_json(self):
        return restore_point_json(self.item)

    def get(self, request, *args, **kwargs):
        return http.HttpResponseNotAllowed(['POST'], 'GET requests are not allowed at this URL.')

class RevertRestorePointView(generic.UpdateView):
    model = RestorePoint
    def get(self, request, *args, **kwargs):
        self.restore_point = self.get_object()
        if not self.restore_point.object.can_be_edited_by(request.user):
            return http.HttpResponseForbidden()

        oei = self.restore_point.object
        project = oei.project
        self.restore_point.revision.revert()

        ei = EditorItem.objects.get(pk=oei.pk)
        ei.project = project
        ei.save()

        return redirect(self.restore_point.object.get_absolute_url())

# JSON representation of a editor.models.StampOfApproval object
def stamp_json(stamp, **kwargs):
    if stamp.pk is None:
        return {
            'pk': None,
            'status': 'draft',
            'status_display': 'Draft',
            'user': None,
        }
    else:
        return {
            'pk': stamp.pk,
            'date': stamp.timelineitem.date.strftime('%Y-%m-%d %H:%M:%S'),
            'status': stamp.status,
            'status_display': stamp.get_status_display(),
            'user': user_json(stamp.user),
        }

# JSON representation of a editor.models.Comment object
def comment_json(comment, **kwargs):
    return {
        'pk': comment.pk,
        'date': comment.timelineitem.date.strftime('%Y-%m-%d %H:%M:%S'),
        'text': comment.text,
        'user': user_json(comment.user),
    }

def restore_point_json(restore_point, **kwargs):
    return {
        'pk': restore_point.pk,
        'date': restore_point.timelineitem.date.strftime('%Y-%m-%d %H:%M:%S'),
        'description': restore_point.description,
        'user': user_json(restore_point.user),
    }

def ability_framework_json(ability_framework):
    return {
        'pk': ability_framework.pk,
        'name': ability_framework.name,
        'description': ability_framework.description,
        'levels': [ability_level_json(l) for l in ability_framework.levels.all()],
    }

def ability_level_json(ability_level):
    return {
        'pk': ability_level.pk,
        'name': ability_level.name,
        'description': ability_level.description,
        'framework': ability_level.framework.pk,
        'start': float(ability_level.start),
        'end': float(ability_level.end),
    }

class DeleteStampView(generic.DeleteView):
    model = NewStampOfApproval

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.can_be_deleted_by(self.request.user):
            self.object.delete()
            ei = self.object.object
            now_current_stamp = EditorItem.objects.get(pk=ei.pk).get_current_stamp()
            data = stamp_json(now_current_stamp)
            return http.HttpResponse(json.dumps({'current_stamp':data}), content_type='application/json')
        else:
            return http.HttpResponseForbidden('You don\'t have the necessary access rights.')

class ShareLinkView(generic.RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        access = kwargs['access']
        try:
            if access == 'edit':
                q = self.model.objects.get(editoritem__share_uuid_edit=kwargs['share_uuid'])
            elif access == 'view':
                q = self.model.objects.get(editoritem__share_uuid_view=kwargs['share_uuid'])
        except (ValueError, self.model.DoesNotExist):
            raise http.Http404

        user = self.request.user
        if access == 'view':
            has_access = q.editoritem.can_be_viewed_by(user)
        elif access == 'edit':
            has_access = q.editoritem.can_be_edited_by(user)
            
        if not has_access:
            try:
                ea = Access.objects.get(item=q.editoritem, user=user)
            except Access.DoesNotExist:
                ea = Access(item=q.editoritem, user=user, access=access)
            ea.access = access
            ea.save()

        return q.get_absolute_url()

class ProjectQuerysetMixin(object):
    """ Set the queryset for the form's project field to the projects available to the user """
    def get_form(self):
        form = super(ProjectQuerysetMixin, self).get_form()
        form.fields['project'].queryset = self.request.user.userprofile.projects().order_by('name')
        return form
