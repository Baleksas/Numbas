from django import template
from django.urls import reverse

register = template.Library()

@register.inclusion_tag('links/question.html')
def question_link(q):
    return {'q': q}

@register.inclusion_tag('links/exam.html')
def exam_link(e):
    return {'e': e}

@register.inclusion_tag('links/editoritem.html')
def editoritem_link(item,show_icon=False,new_tab=False):
    return {'item': item, 'show_icon': show_icon, 'new_tab': new_tab}

@register.simple_tag
def editoritem_url(link, item):
    return reverse('{}_{}'.format(item.editoritem.item_type, link), args=(item.pk, item.editoritem.slug))

@register.inclusion_tag('links/project.html')
def project_link(project):
    return {'project': project}

@register.inclusion_tag('links/add_to_queue_button.html')
def add_to_queue_button(item, show_text=False):
    return {'item': item, 'show_text': show_text}
