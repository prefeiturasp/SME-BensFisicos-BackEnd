from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound


class SafePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        try:
            return super().paginate_queryset(queryset, request, view)
        except NotFound:
            paginator = self.django_paginator_class(queryset, self.page_size)
            self.page = paginator.page(1)
            return list(self.page)