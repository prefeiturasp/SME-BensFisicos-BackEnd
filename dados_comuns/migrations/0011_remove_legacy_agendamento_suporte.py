from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dados_comuns", "0010_historicogeral_justificativa_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP TABLE IF EXISTS agendamento_suporte_intervalohoras CASCADE;
            DROP TABLE IF EXISTS agendamento_suporte_diasemana CASCADE;
            DROP TABLE IF EXISTS agendamento_suporte_agendamentosuporte CASCADE;
            DROP TABLE IF EXISTS agendamento_suporte_configagendasuporte CASCADE;

            DELETE FROM auth_group_permissions
            WHERE permission_id IN (
                SELECT p.id
                FROM auth_permission p
                INNER JOIN django_content_type ct ON ct.id = p.content_type_id
                WHERE ct.app_label = 'agendamento_suporte'
            );

            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_name = 'auth_user_user_permissions'
                ) THEN
                    DELETE FROM auth_user_user_permissions
                    WHERE permission_id IN (
                        SELECT p.id
                        FROM auth_permission p
                        INNER JOIN django_content_type ct ON ct.id = p.content_type_id
                        WHERE ct.app_label = 'agendamento_suporte'
                    );
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_name = 'usuario_usuario_user_permissions'
                ) THEN
                    DELETE FROM usuario_usuario_user_permissions
                    WHERE permission_id IN (
                        SELECT p.id
                        FROM auth_permission p
                        INNER JOIN django_content_type ct ON ct.id = p.content_type_id
                        WHERE ct.app_label = 'agendamento_suporte'
                    );
                END IF;
            END $$;

            DELETE FROM auth_permission
            WHERE content_type_id IN (
                SELECT id FROM django_content_type WHERE app_label = 'agendamento_suporte'
            );

            DELETE FROM django_content_type
            WHERE app_label = 'agendamento_suporte';

            DELETE FROM django_migrations
            WHERE app = 'agendamento_suporte';
            """,
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
