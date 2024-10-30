from django.urls import path
from utilities.urls import get_model_urls
from netbox_rpki.models import RpkiOrganization, RpkiCertificate, RpkiRoa, RpkiRoa
from netbox_rpki import  views

app_name = 'netbox_rpki'

urlpatterns = [
    # RpkiCertificate
    path('certificates/', views.RpkiCertificateListView.as_view(), name='rpkicertificate_list'),
    path('certificates/add/', views.RpkiCertificateEditView.as_view(), name='rpkicertificate_add'),
    path('certificates/<int:pk>/', views.RpkiCertificateView.as_view(), name='rpkicertificate'),
    path('certificates/<int:pk>/edit/', views.RpkiCertificateEditView.as_view(), name='rpkicertificate_edit'),
    path('certificates/<int:pk>/delete/', views.RpkiCertificateDeleteView.as_view(), name='rpkicertificate_delete'),
    path('certificates/<int:pk>/', include(get_model_urls('netbox_rpki', 'rpkicertificate'))),
]
