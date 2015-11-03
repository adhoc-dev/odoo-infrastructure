# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api, _
from openerp.tools import email_split
from openerp.tools import ustr
# import string
# import random
from openerp.exceptions import Warning
import re
import unicodedata
import logging
_logger = logging.getLogger(__name__)


def extract_email(email):
    """ extract the email address from a user-friendly email address """
    addresses = email_split(email)
    return addresses[0] if addresses else ''

# Inspired by http://stackoverflow.com/questions/517923


def remove_accents(input_str):
    """Suboptimal-but-better-than-nothing way to replace accented
    latin letters by an ASCII equivalent. Will obviously change the
    meaning of input_str and work only for some cases"""
    input_str = ustr(input_str)
    nkfd_form = unicodedata.normalize('NFKD', input_str)
    return u''.join([c for c in nkfd_form if not unicodedata.combining(c)])


class database_user(models.Model):
    _name = "infrastructure.database.user"
    _description = "Infrastructure Database User"

    login = fields.Char(
        'Login',
        required=True,
        readonly=True,
        )
    name = fields.Char(
        'Name',
        required=True,
        readonly=True,
        )
    email = fields.Char(
        'Name',
        readonly=True,
        )
    partner_id = fields.Many2one(
        'res.partner',
        'Related Partner',
        )
    user_id = fields.Many2one(
        'res.users',
        'Related User',
        compute='get_user',
        store=True,
        )
    database_id = fields.Many2one(
        'infrastructure.database',
        required=True,
        ondelete='cascade',
        )

    @api.one
    @api.depends('partner_id.user_ids')
    def get_user(self):
        self.user_id = self.env['res.users'].search([
            ('partner_id', '=', self.partner_id.id)], limit=1)

    @api.model
    def get_user_from_ext_id(self, database, external_user_id):
        module_name = 'infra_db_%i_user' % database.id
        return self.env.ref('%s.%s' % (module_name, external_user_id), False)

    @api.multi
    def create_partner(self):
        """ create a new partner
        """
        for record in self:
            if not record.email:
                raise Warning(_('Line dont have email'))
            if record.partner_id:
                raise Warning(_('Line already have a partner'))
            record.partner_id = self.env['res.partner'].create({
                'name': record.name,
                'parent_id': record.partner_id.commercial_partner_id.id,
                'email': record.email,
                'login': record.login,
                }).id

    # TODO ver si dependemos de partner_user o no y si todo esto es necesario
    @api.model
    def _clean_and_make_unique(self, name):
        # when an alias name appears to already be an email, we keep the local
        # part only
        name = remove_accents(name).lower().split('@')[0]
        name = re.sub(r'[^\w+.]+', '.', name)
        return self._find_unique(name)

    @api.model
    def _find_unique(self, name):
        """Find a unique alias name similar to ``name``. If ``name`` is
           already taken, make a variant by adding an integer suffix until
           an unused alias is found.
        """
        sequence = None
        while True:
            new_name = "%s%s" % (
                name, sequence) if sequence is not None else name
            if not self.pool.get('res.users').search(
                    [('login', '=', new_name)]):
                break
            sequence = (sequence + 1) if sequence else 2
        return new_name

    @api.multi
    def create_user(self):
        """ create a new user for partner.partner_id
            @param partner: browse record of model partner.user
            @return: browse record of model res.users
        """
        # TODO ver si queremos que esto sea un parametro o algo por el estilo
        portal_groups = self.env['res.groups'].search(
            [('is_portal', '=', True)])
        if not portal_groups:
            raise Warning(_('No group found with "Is Portal = True"'))

        for record in self:
            partner = record.partner_id
            if not partner:
                raise Warning(_(
                    'No partner selected for database user'))
            if record.user_id:
                raise Warning(_(
                    'There is already a user for partner id %s') % partner.id)
            if partner.email:
                login = extract_email(partner.email)
            else:
                login = record._clean_and_make_unique(
                    partner.name)
            values = {
                'login': login,
                'partner_id': partner.id,
                'company_id': partner.company_id.id,
                'company_ids': [(4, partner.company_id.id)],
                # 'password': ''.join(random.choice(
                #     string.ascii_uppercase + string.digits) for _ in range(6)),
                'groups_id': [(6, 0, [])],
            }
            user = self.env['res.users'].create(values)
            user.write({
                'groups_id': [(6, 0, portal_groups.ids)],
                })
