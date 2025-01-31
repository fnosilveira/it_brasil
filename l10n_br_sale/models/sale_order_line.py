# @ 2019 Akretion - www.akretion.com.br -
#   Magno Costa <magno.costa@akretion.com.br>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from ...l10n_br_fiscal.constants.fiscal import TAX_FRAMEWORK


class SaleOrderLine(models.Model):
    _name = 'sale.order.line'
    _inherit = [_name, 'l10n_br_fiscal.document.line.mixin']

    @api.model
    def _default_fiscal_operation(self):
        return self.env.user.company_id.sale_fiscal_operation_id

    @api.model
    def _fiscal_operation_domain(self):
        domain = [('state', '=', 'approved')]
        return domain

    fiscal_operation_id = fields.Many2one(
        comodel_name='l10n_br_fiscal.operation',
        default=_default_fiscal_operation,
        domain=lambda self: self._fiscal_operation_domain())

    # Adapt Mixin's fields
    fiscal_tax_ids = fields.Many2many(
        comodel_name='l10n_br_fiscal.tax',
        relation='fiscal_sale_line_tax_rel',
        column1='document_id',
        column2='fiscal_tax_id',
        string='Fiscal Taxes',
    )

    quantity = fields.Float(
        string="Product Uom Quantity",
        related="product_uom_qty",
        depends=["product_uom_qty"],
    )

    fiscal_qty_delivered = fields.Float(
        string="Fiscal Utm Qty Delivered",
        compute="_compute_qty_delivered",
        compute_sudo=True,
        store=True,
        digits='Product Unit of Measure',
    )

    uom_id = fields.Many2one(
        related='product_uom',
        depends=['product_uom'],
    )

    tax_framework = fields.Selection(
        selection=TAX_FRAMEWORK,
        related='order_id.company_id.tax_framework',
        string='Tax Framework',
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        related='order_id.partner_id',
        string='Partner',
    )

    # Add Fields in model sale.order.line
    price_gross = fields.Monetary(
        compute='_compute_amount',
        string='Gross Amount',
        default=0.00,
    )

    other_costs_value = fields.Monetary(
        string='Other Costs',
        default=0.00,
    )

    comment_ids = fields.Many2many(
        comodel_name='l10n_br_fiscal.comment',
        relation='sale_order_line_comment_rel',
        column1='sale_line_id',
        column2='comment_id',
        string='Comments',
    )

    ind_final = fields.Selection(related="order_id.ind_final")

    def _get_protected_fields(self):
        protected_fields = super()._get_protected_fields()
        return protected_fields + [
            'fiscal_tax_ids', 'fiscal_operation_id',
            'fiscal_operation_line_id',
        ]

    # @api.depends(
    #     'product_uom_qty',
    #     'price_unit',
    #     'discount',
    #     'fiscal_price',
    #     'fiscal_quantity',
    #     'discount_value',
    #     'freight_value',
    #     'insurance_value',
    #     'other_costs_value',
    #     'tax_id')
    # def _compute_amount(self):
    #     """Compute the amounts of the SO line."""
    #     import pudb;pu.db
    #     amount_untaxed = self.amount_untaxed 
    #     super()._compute_amount()
    #     for l in self:
    #         l._update_taxes()
    #         l._compute_amounts()
    #         price_tax = l.amount_tax_included + l.amount_tax_not_included
    #         price_total = (
    #              l.price_subtotal + l.freight_value +
    #              l.insurance_value + l.other_costs_value)
    #         l.update({
    #             'price_subtotal': l.amount_untaxed,
    #             'price_tax': price_tax,
    #             'price_gross': price_total,
    #             'price_total': price_total,
    #             'amount_taxed': self.amount_untaxed
    #         })

    @api.depends(
        "product_uom_qty",
        "price_unit",
        "fiscal_price",
        "fiscal_quantity",
        "discount_value",
        "freight_value",
        "insurance_value",
        "other_value",
        "tax_id",
    )
    def _compute_amount(self):
        """Compute the amounts of the PO line."""
        super()._compute_amount()
        for line in self:
            # Update taxes fields
            line._update_taxes()
            # Call mixin compute method
            line._compute_amounts()
            # Update record
            line.update(
                {
                    "price_subtotal": line.amount_untaxed,
                    "price_tax": line.amount_tax,
                    "price_total": line.amount_total,
                }
            )

    # def _prepare_invoice_line(self, **optional_values):
    #     self.ensure_one()
    #     result = self._prepare_br_fiscal_dict()
    #     vals = super()._prepare_invoice_line(**optional_values)
    #     if self.product_id and self.product_id.invoice_policy == "delivery":
    #         result["fiscal_quantity"] = self.fiscal_qty_delivered
    #         vals['quantity'] = self.fiscal_qty_delivered
    #     return vals

    def _prepare_account_move_line(self, move=False):
        values = super()._prepare_account_move_line(move)
        if values.get("sale_line_id"):
            line = self.env["sale.order.line"].browse(
                values.get("sale_line_id")
            )
            fiscal_values = line._prepare_br_fiscal_dict()
            fiscal_values.update(values)
            values.update(fiscal_values)

        return values

    @api.onchange('product_uom', 'product_uom_qty')
    def _onchange_product_uom(self):
        """To call the method in the mixin to update
        the price and fiscal quantity."""
        self._onchange_commercial_quantity()

    @api.depends(
        "qty_delivered_method",
        "qty_delivered_manual",
        "analytic_line_ids.so_line",
        "analytic_line_ids.unit_amount",
        "analytic_line_ids.product_uom_id",
    )
    def _compute_qty_delivered(self):
        super()._compute_qty_delivered()
        for line in self:
            line.fiscal_qty_delivered = 0.0
            if line.product_id.invoice_policy == "delivery":
                if line.uom_id == line.uot_id:
                    line.fiscal_qty_delivered = line.qty_delivered

            if line.uom_id != line.uot_id:
                line.fiscal_qty_delivered = (
                    line.qty_delivered * line.product_id.uot_factor
                )

    @api.onchange('discount')
    def _onchange_discount_percent(self):
        """Update discount value"""
        if not self.env.user.has_group('l10n_br_sale.group_discount_per_value'):
            if self.discount:
                self.discount_value = (
                    (self.product_uom_qty * self.price_unit)
                    * (self.discount / 100)
                )

    @api.onchange('discount_value')
    def _onchange_discount_value(self):
        """Update discount percent"""
        if self.env.user.has_group('l10n_br_sale.group_discount_per_value'):
            if self.discount_value:
                self.discount = ((self.discount_value * 100) /
                                 (self.product_uom_qty * self.price_unit))

    def _compute_tax_id(self):
        super(SaleOrderLine, self)._compute_tax_id()
        for line in self:
            line.tax_id |= line.fiscal_tax_ids.account_taxes(user_type="sale")

    @api.onchange("fiscal_tax_ids")
    def _onchange_fiscal_tax_ids(self):
        super()._onchange_fiscal_tax_ids()
        self._compute_tax_id()

    @api.onchange("fiscal_operation_line_id")
    def _onchange_fiscal_operation_line_id(self):
        super()._onchange_fiscal_operation_line_id()
