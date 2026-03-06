from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = 'res.partner'

    national_id_number = fields.Char(string='National ID / Passport Number', help="Identification strictly for pawn shop record keeping")
    national_id_image_front = fields.Binary(string='ID/Passport Image (Front)', attachment=True)
    national_id_image_back = fields.Binary(string='ID/Passport Image (Back)', attachment=True)

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        if name and operator in ('=', 'ilike', '=ilike', 'like', '=like'):
            # Allow searching by National ID Number anywhere the partner is searched
            args = ['|', ('national_id_number', operator, name)] + args
        return super()._name_search(name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid)
