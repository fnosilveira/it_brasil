# See LICENSE file for full copyright and licensing details.


from odoo import _, api, models
from odoo.exceptions import UserError


class Picking(models.Model):
    _inherit = "stock.picking"


    def button_validate(self):
        # TODO validar se o usuario é gerente se for executar somente o return ultima linha
        limite_disponivel = self.partner_id._check_limit()
        if limite_disponivel < 0:
            msg = 'Your available credit limit' \
                  ' Amount = %s \nCheck "%s" Accounts or Credit ' \
                  'Limits.' % (limite_disponivel,
                  self.partner_id.name)
            raise UserError(_('You can not confirm Sale '
                                'Order. \n' + msg))
        return super(Picking, self).button_validate()