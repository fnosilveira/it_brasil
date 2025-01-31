# Copyright (C) 2009 - TODAY Renato Lima - Akretion
# Copyright (C) 2019 - TODAY Raphaël Valyi - Akretion
# Copyright (C) 2020 - TODAY Luis Felipe Mileo - KMEE
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
# pylint: disable=api-one-deprecated


from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_br_fiscal.constants.fiscal import (
    DOCUMENT_ISSUER_COMPANY,
    DOCUMENT_ISSUER_PARTNER,
    FISCAL_OUT,
    SITUACAO_EDOC_CANCELADA,
    SITUACAO_EDOC_EM_DIGITACAO,
)

MOVE_TO_OPERATION = {
    "out_invoice": "out",
    "in_invoice": "in",
    "out_refund": "in",
    "in_refund": "out",
}

REFUND_TO_OPERATION = {
    "out_invoice": "in",
    "in_invoice": "out",
    "out_refund": "out",
    "in_refund": "in",
}

FISCAL_TYPE_REFUND = {
    "out": ["purchase_refund", "in_return"],
    "in": ["sale_refund", "out_return"],
}

MOVE_TAX_USER_TYPE = {
    "out_invoice": "sale",
    "in_invoice": "purchase",
    "out_refund": "sale",
    "in_refund": "purchase",
}

SHADOWED_FIELDS = [
    "partner_id",
    "company_id",
    "currency_id",
    "partner_shipping_id",
]


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = [
        _name,
        "l10n_br_fiscal.document.mixin.methods",
        "l10n_br_fiscal.document.invoice.mixin",
    ]
    _inherits = {"l10n_br_fiscal.document": "fiscal_document_id"}
    _order = "date DESC, name DESC"

    # initial account.invoice inherits on fiscal.document that are
    # disable with active=False in their fiscal_document table.
    # To make these invoices still visible, we set active=True
    # in the invoice table.
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    cnpj_cpf = fields.Char(
        string="CNPJ/CPF",
        related="partner_id.cnpj_cpf",
    )

    legal_name = fields.Char(
        string="Adapted Legal Name",
        related="partner_id.legal_name",
    )

    ie = fields.Char(
        string="Adapted State Tax Number",
        related="partner_id.inscr_est",
    )

    document_electronic = fields.Boolean(
        related="document_type_id.electronic",
        string="Electronic?",
    )

    # this default should be overwritten to False in a module pretending to
    # create fiscal documents from the invoices. But this default here
    # allows to install the l10n_br_account module without creating issues
    # with the existing Odoo invoice (demo or not).
    fiscal_document_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.document",
        string="Fiscal Document",
        required=True,
        copy=False,
        ondelete="cascade",
    )

    document_type = fields.Char(
        related="document_type_id.code",
        string="Document Code",
        store=True,
    )

    def _get_amount_lines(self):
        """Get object lines instaces used to compute fields"""
        return self.mapped("invoice_line_ids")

    @api.model
    def _shadowed_fields(self):
        """Returns the list of shadowed fields that are synced
        from the parent."""
        return SHADOWED_FIELDS

    def _prepare_shadowed_fields_dict(self, default=False):
        self.ensure_one()
        vals = self._convert_to_write(self.read(self._shadowed_fields())[0])
        if default:  # in case you want to use new rather than write later
            return {"default_%s" % (k,): vals[k] for k in vals.keys()}
        return vals

    def _write_shadowed_fields(self):
        for invoice in self:
            if invoice.document_type_id:
                shadowed_fiscal_vals = invoice._prepare_shadowed_fields_dict()
                invoice.fiscal_document_id.write(shadowed_fiscal_vals)

    @api.model
    def fields_view_get(
        self, view_id=None, view_type="form", toolbar=False, submenu=False
    ):
        invoice_view = super().fields_view_get(view_id, view_type, toolbar, submenu)
        if view_type == "form":
            view = self.env["ir.ui.view"]

            if view_id == self.env.ref("l10n_br_account.fiscal_invoice_form").id:
                invoice_line_form_id = self.env.ref(
                    "l10n_br_account.fiscal_invoice_line_form"
                ).id
                sub_form_view = self.env["account.move.line"].fields_view_get(
                    view_id=invoice_line_form_id, view_type="form"
                )["arch"]
                sub_form_node = self.env["account.move.line"].inject_fiscal_fields(
                    sub_form_view
                )
                sub_arch, sub_fields = view.postprocess_and_fields(
                    sub_form_node, "account.move.line", False
                )
                line_field_name = "invoice_line_ids"
                invoice_view["fields"][line_field_name]["views"]["form"] = {
                    "fields": sub_fields,
                    "arch": sub_arch,
                }

            else:
                if invoice_view["fields"].get("invoice_line_ids"):
                    invoice_line_form_id = self.env.ref(
                        "l10n_br_account.invoice_form"
                    ).id
                    sub_form_view = invoice_view["fields"]["invoice_line_ids"]["views"][
                        "form"
                    ]["arch"]

                    sub_form_node = self.env["account.move.line"].inject_fiscal_fields(
                        sub_form_view
                    )
                    sub_arch, sub_fields = view.postprocess_and_fields(
                        sub_form_node, "account.move.line", False
                    )
                    line_field_name = "invoice_line_ids"
                    invoice_view["fields"][line_field_name]["views"]["form"] = {
                        "fields": sub_fields,
                        "arch": sub_arch,
                    }

                if invoice_view["fields"].get("line_ids"):
                    invoice_line_form_id = self.env.ref(
                        "l10n_br_account.invoice_form"
                    ).id
                    sub_form_view = invoice_view["fields"]["line_ids"]["views"]["tree"][
                        "arch"
                    ]

                    sub_form_node = self.env["account.move.line"].inject_fiscal_fields(
                        sub_form_view
                    )
                    sub_arch, sub_fields = view.postprocess_and_fields(
                        sub_form_node, "account.move.line", False
                    )
                    line_field_name = "line_ids"
                    invoice_view["fields"][line_field_name]["views"]["tree"] = {
                        "fields": sub_fields,
                        "arch": sub_arch,
                    }

        return invoice_view

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        move_type = self.env.context.get("default_move_type", "out_invoice")
        # acrescentei o if abaixo com o return dava erro ao adicionar um diario qualquer
        if move_type == 'entry':
            return defaults
        defaults["fiscal_operation_type"] = MOVE_TO_OPERATION[move_type]
        if defaults["fiscal_operation_type"] == FISCAL_OUT:
            defaults["issuer"] = DOCUMENT_ISSUER_COMPANY
        else:
            defaults["issuer"] = DOCUMENT_ISSUER_PARTNER
        return defaults

    @api.model_create_multi
    def create(self, values):
        for vals in values:
            if not vals.get("document_type_id"):
                vals["fiscal_document_id"] = self.env.company.fiscal_dummy_id.id
        invoice = super().create(values)

        # quando cria uma fatura diretamente em faturamento 
        # nao esta gravando os campos abaixo
        # for ln in invoice.invoice_line_ids:
        #     if not ln.icms_cst_id:
        #         if 'invoice_line_ids' in values:
        #             for lnv in values['invoice_line_ids']:
        #                 if 'icms_cst_id' in lnv[2] and lnv[2]['icms_cst_id'] and \
        #                     lnv[2]['product_id'] == ln.product_id.id:
        #                     ln.update({
        #                         'icms_cst_id': lnv[2]['icms_cst_id'],
        #                         'ipi_cst_id': lnv[2]['ipi_cst_id'],
        #                         'pis_cst_id': lnv[2]['pis_cst_id'],
        #                         'cofins_cst_id': lnv[2]['cofins_cst_id'],
        #                     })
        #     if not ln.ncm_id:
        #         if 'invoice_line_ids' in values:
        #             for lnv in values['invoice_line_ids']:
        #                 if 'ncm_id' in lnv[2] and lnv[2]['ncm_id'] and \
        #                     lnv[2]['product_id'] == ln.product_id.id:
        #                     ln.update({
        #                         'ncm_id': lnv[2]['ncm_id'],
        #                         'cest_id': lnv[2]['cest_id'],
        #                     })

        invoice._write_shadowed_fields()
        return invoice

    def write(self, values):
        result = super().write(values)
        self._write_shadowed_fields()
        return result

    def unlink(self):
        """Allows delete a draft or cancelled invoices"""
        unlink_moves = self.env["account.move"]
        unlink_documents = self.env["l10n_br_fiscal.document"]
        for move in self:
            if not move.exists():
                continue
            if (
                move.fiscal_document_id
                and move.fiscal_document_id.id != self.env.company.fiscal_dummy_id.id
            ):
                unlink_documents |= move.fiscal_document_id
            unlink_moves |= move
        result = super(AccountMove, unlink_moves).unlink()
        unlink_documents.unlink()
        self.clear_caches()
        return result

    @api.returns("self", lambda value: value.id)
    def copy(self, default=None):
        default = default or {}
        if self.document_type_id:
            default["fiscal_line_ids"] = False
        else:
            default["line_ids"] = self.line_ids[0]
        return super().copy(default)

    def _recompute_tax_lines(self, recompute_tax_base_amount=False):
        """ Compute the dynamic tax lines of the journal entry.
        :param recompute_tax_base_amount: Flag forcing only the recomputation of the `tax_base_amount` field.
        """
        self.ensure_one()
        in_draft_mode = self != self._origin

        def _serialize_tax_grouping_key(grouping_dict):
            ''' Serialize the dictionary values to be used in the taxes_map.
            :param grouping_dict: The values returned by '_get_tax_grouping_key_from_tax_line' or '_get_tax_grouping_key_from_base_line'.
            :return: A string representing the values.
            '''
            return '-'.join(str(v) for v in grouping_dict.values())

        def _compute_base_line_taxes(base_line):
            ''' Compute taxes amounts both in company currency / foreign currency as the ratio between
            amount_currency & balance could not be the same as the expected currency rate.
            The 'amount_currency' value will be set on compute_all(...)['taxes'] in multi-currency.
            :param base_line:   The account.move.line owning the taxes.
            :return:            The result of the compute_all method.
            '''
            move = base_line.move_id

            if move.is_invoice(include_receipts=True):
                handle_price_include = True
                sign = -1 if move.is_inbound() else 1
                quantity = base_line.quantity
                is_refund = move.move_type in ('out_refund', 'in_refund')
                price_unit_wo_discount = sign * base_line.price_unit * (1 - (base_line.discount / 100.0))
            else:
                handle_price_include = False
                quantity = 1.0
                tax_type = base_line.tax_ids[0].type_tax_use if base_line.tax_ids else None
                is_refund = (tax_type == 'sale' and base_line.debit) or (tax_type == 'purchase' and base_line.credit)
                price_unit_wo_discount = base_line.amount_currency

            balance_taxes_res = base_line.tax_ids._origin.with_context(force_sign=move._get_tax_force_sign()).compute_all(
                price_unit_wo_discount,
                currency=base_line.currency_id,
                quantity=quantity,
                product=base_line.product_id,
                partner=base_line.partner_id,
                is_refund=is_refund,
                handle_price_include=handle_price_include,
                fiscal_taxes=base_line.fiscal_tax_ids,
                operation_line=base_line.fiscal_operation_line_id,
                ncm=base_line.ncm_id,
                nbs=base_line.nbs_id,
                nbm=base_line.nbm_id,
                cest=base_line.cest_id,
                discount_value=base_line.discount_value,
                insurance_value=base_line.insurance_value,
                other_value=base_line.other_value,
                freight_value=base_line.freight_value,
                fiscal_price=base_line.fiscal_price,
                fiscal_quantity=base_line.fiscal_quantity,
                uot=base_line.uot_id,
                icmssn_range=base_line.icmssn_range_id,
                icms_origin=base_line.icms_origin
            )
            if move.move_type == 'entry':
                repartition_field = is_refund and 'refund_repartition_line_ids' or 'invoice_repartition_line_ids'
                repartition_tags = base_line.tax_ids.flatten_taxes_hierarchy().mapped(repartition_field).filtered(lambda x: x.repartition_type == 'base').tag_ids
                tags_need_inversion = self._tax_tags_need_inversion(move, is_refund, tax_type)
                if tags_need_inversion:
                    balance_taxes_res['base_tags'] = base_line._revert_signed_tags(repartition_tags).ids
                    for tax_res in balance_taxes_res['taxes']:
                        tax_res['tag_ids'] = base_line._revert_signed_tags(self.env['account.account.tag'].browse(tax_res['tag_ids'])).ids

            return balance_taxes_res

        taxes_map = {}

        # ==== Add tax lines ====
        to_remove = self.env['account.move.line']
        for line in self.line_ids.filtered('tax_repartition_line_id'):
            grouping_dict = self._get_tax_grouping_key_from_tax_line(line)
            grouping_key = _serialize_tax_grouping_key(grouping_dict)
            if grouping_key in taxes_map:
                # A line with the same key does already exist, we only need one
                # to modify it; we have to drop this one.
                to_remove += line
            else:
                taxes_map[grouping_key] = {
                    'tax_line': line,
                    'amount': 0.0,
                    'tax_base_amount': 0.0,
                    'grouping_dict': False,
                }
        if not recompute_tax_base_amount:
            self.line_ids -= to_remove

        # ==== Mount base lines ====
        for line in self.line_ids.filtered(lambda line: not line.tax_repartition_line_id):
            # Don't call compute_all if there is no tax.
            if not line.tax_ids:
                if not recompute_tax_base_amount:
                    line.tax_tag_ids = [(5, 0, 0)]
                continue

            compute_all_vals = _compute_base_line_taxes(line)

            # Assign tags on base line
            if not recompute_tax_base_amount:
                line.tax_tag_ids = compute_all_vals['base_tags'] or [(5, 0, 0)]

            tax_exigible = True
            for tax_vals in compute_all_vals['taxes']:
                grouping_dict = self._get_tax_grouping_key_from_base_line(line, tax_vals)
                grouping_key = _serialize_tax_grouping_key(grouping_dict)

                tax_repartition_line = self.env['account.tax.repartition.line'].browse(tax_vals['tax_repartition_line_id'])
                tax = tax_repartition_line.invoice_tax_id or tax_repartition_line.refund_tax_id

                if tax.tax_exigibility == 'on_payment':
                    tax_exigible = False

                taxes_map_entry = taxes_map.setdefault(grouping_key, {
                    'tax_line': None,
                    'amount': 0.0,
                    'tax_base_amount': 0.0,
                    'grouping_dict': False,
                })
                taxes_map_entry['amount'] += tax_vals['amount']
                taxes_map_entry['tax_base_amount'] += self._get_base_amount_to_display(tax_vals['base'], tax_repartition_line, tax_vals['group'])
                taxes_map_entry['grouping_dict'] = grouping_dict
            if not recompute_tax_base_amount:
                line.tax_exigible = tax_exigible

        # ==== Pre-process taxes_map ====
        taxes_map = self._preprocess_taxes_map(taxes_map)

        # ==== Process taxes_map ====
        for taxes_map_entry in taxes_map.values():
            # The tax line is no longer used in any base lines, drop it.
            if taxes_map_entry['tax_line'] and not taxes_map_entry['grouping_dict']:
                if not recompute_tax_base_amount:
                    self.line_ids -= taxes_map_entry['tax_line']
                continue

            currency = self.env['res.currency'].browse(taxes_map_entry['grouping_dict']['currency_id'])

            # Don't create tax lines with zero balance.
            if currency.is_zero(taxes_map_entry['amount']):
                if taxes_map_entry['tax_line'] and not recompute_tax_base_amount:
                    self.line_ids -= taxes_map_entry['tax_line']
                continue

            # tax_base_amount field is expressed using the company currency.
            tax_base_amount = currency._convert(taxes_map_entry['tax_base_amount'], self.company_currency_id, self.company_id, self.date or fields.Date.context_today(self))

            # Recompute only the tax_base_amount.
            if recompute_tax_base_amount:
                if taxes_map_entry['tax_line']:
                    taxes_map_entry['tax_line'].tax_base_amount = tax_base_amount
                continue

            balance = currency._convert(
                taxes_map_entry['amount'],
                self.company_currency_id,
                self.company_id,
                self.date or fields.Date.context_today(self),
            )
            to_write_on_line = {
                'amount_currency': taxes_map_entry['amount'],
                'currency_id': taxes_map_entry['grouping_dict']['currency_id'],
                'debit': balance > 0.0 and balance or 0.0,
                'credit': balance < 0.0 and -balance or 0.0,
                'tax_base_amount': tax_base_amount,
            }

            if taxes_map_entry['tax_line']:
                # Update an existing tax line.
                taxes_map_entry['tax_line'].update(to_write_on_line)
            else:
                # Create a new tax line.
                create_method = in_draft_mode and self.env['account.move.line'].new or self.env['account.move.line'].create
                tax_repartition_line_id = taxes_map_entry['grouping_dict']['tax_repartition_line_id']
                tax_repartition_line = self.env['account.tax.repartition.line'].browse(tax_repartition_line_id)
                tax = tax_repartition_line.invoice_tax_id or tax_repartition_line.refund_tax_id
                taxes_map_entry['tax_line'] = create_method({
                    **to_write_on_line,
                    'name': tax.name,
                    'move_id': self.id,
                    'partner_id': line.partner_id.id,
                    'company_id': line.company_id.id,
                    'company_currency_id': line.company_currency_id.id,
                    'tax_base_amount': tax_base_amount,
                    'exclude_from_invoice_tab': True,
                    'tax_exigible': tax.tax_exigibility == 'on_invoice',
                    **taxes_map_entry['grouping_dict'],
                })

            if in_draft_mode:
                taxes_map_entry['tax_line'].update(taxes_map_entry['tax_line']._get_fields_onchange_balance(force_computation=True))   

    @api.model
    def invoice_line_move_line_get(self):
        move_lines_dict = super().invoice_line_move_line_get()
        new_mv_lines_dict = []
        for line in move_lines_dict:
            invoice_line = self.line_ids.filtered(lambda l: l.id == line.get("invl_id"))

            if invoice_line.fiscal_operation_id:
                if invoice_line.fiscal_operation_id.deductible_taxes:
                    line["price"] = invoice_line.price_total
                else:
                    line["price"] = invoice_line.price_total - (
                        invoice_line.amount_tax_withholding
                        + invoice_line.amount_tax_included
                    )

            if invoice_line.cfop_id:
                if invoice_line.cfop_id.finance_move:
                    new_mv_lines_dict.append(line)
            else:
                new_mv_lines_dict.append(line)

        return new_mv_lines_dict

    @api.model
    def tax_line_move_line_get(self):
        tax_lines_dict = super().tax_line_move_line_get()
        if self.fiscal_operation_id and self.fiscal_operation_id.deductible_taxes:
            for tax_line in self.tax_line_ids:
                analytic_tag_ids = [
                    (4, analytic_tag.id, None)
                    for analytic_tag in tax_line.analytic_tag_ids
                ]

                deductible_tax = tax_line.tax_id.tax_group_id.deductible_tax(
                    INVOICE_TAX_USER_TYPE[self.type]
                )

                if deductible_tax:
                    account = deductible_tax.account_id or tax_line.account_id
                    tax_line_vals = {
                        "invoice_tax_line_id": tax_line.id,
                        "tax_line_id": tax_line.tax_id.id,
                        "type": "tax",
                        "name": tax_line.name or deductible_tax.name,
                        "price_unit": tax_line.amount_total * -1,
                        "quantity": 1,
                        "price": tax_line.amount_total * -1,
                        "account_id": account.id,
                        "account_analytic_id": tax_line.account_analytic_id.id,
                        "analytic_tag_ids": analytic_tag_ids,
                        "move_id": self.id,
                    }
                    tax_lines_dict.append(tax_line_vals)

        return tax_lines_dict

    # def finalize_invoice_move_lines(self, move_lines):
    #     lines = super().finalize_invoice_move_lines(move_lines)
    #     financial_lines = [
    #         line for line in lines if line[2]["account_id"] == self.account_id.id
    #     ]
    #     count = 1

    #     for line in financial_lines:
    #         if line[2]["debit"] or line[2]["credit"]:
    #             if self.document_type_id:
    #                 line[2]["name"] = "{}/{}-{}".format(
    #                     self.fiscal_document_id.with_context(
    #                         fiscal_document_no_company=True
    #                     )._compute_document_name(),
    #                     count,
    #                     len(financial_lines),
    #                 )
    #                 count += 1
    #     return lines

    # def get_taxes_values(self):
    #     tax_grouped = {}
    #     round_curr = self.currency_id.round
    #     for line in self.line_ids:
    #         if not line.account_id or line.display_type:
    #             continue

    #         computed_taxes = line.tax_ids.compute_all(
    #             price_unit=line.price_unit,
    #             currency=line.move_id.currency_id,
    #             quantity=line.quantity,
    #             product=line.product_id,
    #             partner=line.move_id.partner_id,
    #             fiscal_taxes=line.fiscal_tax_ids,
    #             operation_line=line.fiscal_operation_line_id,
    #             ncm=line.ncm_id,
    #             nbs=line.nbs_id,
    #             nbm=line.nbm_id,
    #             cest=line.cest_id,
    #             discount_value=line.discount_value,
    #             insurance_value=line.insurance_value,
    #             other_value=line.other_value,
    #             freight_value=line.freight_value,
    #             fiscal_price=line.fiscal_price,
    #             fiscal_quantity=line.fiscal_quantity,
    #             uot=line.uot_id,
    #             icmssn_range=line.icmssn_range_id,
    #         )["taxes"]

    #         for tax in computed_taxes:
    #             if tax.get("amount", 0.0) != 0.0:
    #                 val = self._prepare_tax_line_vals(line, tax)
    #                 key = (
    #                     self.env["account.tax"].browse(tax["id"]).get_grouping_key(val)
    #                 )

    #                 if key not in tax_grouped:
    #                     tax_grouped[key] = val
    #                     tax_grouped[key]["base"] = round_curr(val["base"])
    #                 else:
    #                     tax_grouped[key]["amount"] += val["amount"]
    #                     tax_grouped[key]["base"] += round_curr(val["base"])
    #     return tax_grouped

    @api.onchange("fiscal_operation_id")
    def _onchange_fiscal_operation_id(self):
        super()._onchange_fiscal_operation_id()
        if self.fiscal_operation_id and self.fiscal_operation_id.journal_id:
            self.journal_id = self.fiscal_operation_id.journal_id

    def open_fiscal_document(self):
        if self.env.context.get("move_type", "") == "out_invoice":
            action = self.env.ref("l10n_br_account.fiscal_invoice_out_action").read()[0]
        elif self.env.context.get("move_type", "") == "in_invoice":
            action = self.env.ref("l10n_br_account.fiscal_invoice_in_action").read()[0]
        else:
            action = self.env.ref("l10n_br_account.fiscal_invoice_all_action").read()[0]
        form_view = [(self.env.ref("l10n_br_account.fiscal_invoice_form").id, "form")]
        if "views" in action:
            action["views"] = form_view + [
                (state, view) for state, view in action["views"] if view != "form"
            ]
        else:
            action["views"] = form_view
        action["res_id"] = self.id
        return action

    def action_date_assign(self):
        """Usamos esse método para definir a data de emissão do documento
        fiscal e numeração do documento fiscal para ser usado nas linhas
        dos lançamentos contábeis."""
        super().action_date_assign()
        for invoice in self:
            if invoice.document_type_id:
                if invoice.issuer == DOCUMENT_ISSUER_COMPANY:
                    if (
                        not invoice.comment_ids
                        and invoice.fiscal_operation_id.comment_ids
                    ):
                        invoice.comment_ids |= self.fiscal_operation_id.comment_ids

                    for line in invoice.line_ids:
                        if (
                            not line.comment_ids
                            and line.fiscal_operation_line_id.comment_ids
                        ):
                            line.comment_ids |= (
                                line.fiscal_operation_line_id.comment_ids
                            )

                    invoice.fiscal_document_id._document_date()
                    invoice.fiscal_document_id._document_number()

    def button_draft(self):        
        for i in self.filtered(lambda d: d.document_type_id):
            if i.state_edoc == SITUACAO_EDOC_CANCELADA:
                if i.issuer == DOCUMENT_ISSUER_COMPANY:
                    raise UserError(
                        _(
                            "You can't set this document number: {} to draft "
                            "because this document is cancelled in SEFAZ".format(
                                i.document_number
                            )
                        )
                    )
            if i.state_edoc != SITUACAO_EDOC_EM_DIGITACAO:
                i.fiscal_document_id.action_document_back2draft()
        return super().button_draft()

    def action_document_send(self):
        invoices = self.filtered(lambda d: d.document_type_id)
        if invoices:
            invoices.mapped("fiscal_document_id").action_document_send()
            for invoice in invoices:
                # da erro na linha abaixo
                # invoice.move_id.post(invoice=invoice)
                invoice.fiscal_document_id.action_document_send()

    def action_document_cancel(self):
        for i in self.filtered(lambda d: d.document_type_id):
            return i.fiscal_document_id.action_document_cancel()

    def action_document_correction(self):
        for i in self.filtered(lambda d: d.document_type_id):
            return i.fiscal_document_id.action_document_correction()

    def action_document_invalidate(self):
        for i in self.filtered(lambda d: d.document_type_id):
            return i.fiscal_document_id.action_document_invalidate()

    def action_document_back2draft(self):
        """Sets fiscal document to draft state and cancel and set to draft
        the related invoice for both documents remain equivalent state."""
        for i in self.filtered(lambda d: d.document_type_id):
            i.button_cancel
            i.button_draft
            # i.fiscal_document_id._change_state('em_digitacao')

    def action_invoice_cancel(self):
        for i in self.filtered(lambda d: d.document_type_id):
            i.fiscal_document_id.action_document_cancel()
        return super().action_invoice_cancel()

    def action_post(self):
        result = super().action_post()

        self.mapped("fiscal_document_id").filtered(
            lambda d: d.document_type_id
        ).action_document_confirm()

        # TODO FIXME
        # Deixar a migração das funcionalidades do refund por último.
        # Verificar se ainda haverá necessidade desse código.

        # for record in self.filtered(lambda i: i.refund_move_id):
        #     if record.state == "open":
        #         # Ao confirmar uma fatura/documento fiscal se é uma devolução
        #         # é feito conciliado com o documento de origem para abater
        #         # o valor devolvido pelo documento de refund
        #         to_reconcile_lines = self.env["account.move.line"]
        #         for line in record.move_id.line_ids:
        #             if line.account_id.id == record.account_id.id:
        #                 to_reconcile_lines += line
        #             if line.reconciled:
        #                 line.remove_move_reconcile()
        #         for line in record.refund_move_id.move_id.line_ids:
        #             if line.account_id.id == record.refund_move_id.account_id.id:
        #                 to_reconcile_lines += line

        #         to_reconcile_lines.filtered(lambda l: l.reconciled).reconcile()

        return result

    def button_cancel(self):
        for i in self.filtered(lambda d: d.document_type_id):
            i.fiscal_document_id.action_document_cancel()
        return super().button_cancel()

    def view_xml(self):
        self.ensure_one()
        return self.fiscal_document_id.view_xml()

    def view_pdf(self):
        self.ensure_one()
        return self.fiscal_document_id.view_pdf()

    def action_send_email(self):
        self.ensure_one()
        return self.fiscal_document_id.action_send_email()

    # TODO FIXME migrate. refund method are very different in Odoo 13+
    # def _get_refund_common_fields(self):
    #     fields = super()._get_refund_common_fields()
    #     fields += [
    #         "fiscal_operation_id",
    #         "document_type_id",
    #         "document_serie_id",
    #     ]
    #     return fields

    # @api.returns("self")
    # def refund(self, date=None, date=None, description=None, journal_id=None):
    #     new_invoices = super().refund(date, date, description, journal_id)

    #     force_fiscal_operation_id = False
    #     if self.env.context.get("force_fiscal_operation_id"):
    #         force_fiscal_operation_id = self.env["l10n_br_fiscal.operation"].browse(
    #             self.env.context.get("force_fiscal_operation_id")
    #         )

    #     for record in new_invoices.filtered(lambda i: i.document_type_id):
    #         if (
    #             not force_fiscal_operation_id
    #             and not record.fiscal_operation_id.return_fiscal_operation_id
    #         ):
    #             raise UserError(
    #                 _("""Document without Return Fiscal Operation! \n Force one!""")
    #             )

    #         record.fiscal_operation_id = (
    #             force_fiscal_operation_id
    #             or record.fiscal_operation_id.return_fiscal_operation_id
    #         )
    #         record.fiscal_document_id._onchange_fiscal_operation_id()

    #         for line in record.line_ids:
    #             if (
    #                 not force_fiscal_operation_id
    #                 and not line.fiscal_operation_id.return_fiscal_operation_id
    #             ):
    #                 raise UserError(
    #                     _(
    #                         """Line without Return Fiscal Operation! \n
    #                         Please force one! \n{}""".format(
    #                             line.name
    #                         )
    #                     )
    #                 )

    #             line.fiscal_operation_id = (
    #                 force_fiscal_operation_id
    #                 or line.fiscal_operation_id.return_fiscal_operation_id
    #             )
    #             line._onchange_fiscal_operation_id()

    #         refund_inv_id = record.refund_move_id

    #         if record.refund_move_id.document_type_id:
    #             record.fiscal_document_id._document_reference(
    #                 refund_inv_id.fiscal_document_id
    #             )

    #     return new_invoices

    # def _refund_cleanup_lines(self, lines):
    #     result = super()._refund_cleanup_lines(lines)
    #     for _a, _b, vals in result:
    #         if vals.get("fiscal_document_line_id"):
    #             vals.pop("fiscal_document_line_id")

    #     for i, line in enumerate(lines):
    #         for name, _field in line._fields.items():
    #             if name == "fiscal_tax_ids":
    #                 result[i][2][name] = [(6, 0, line[name].ids)]

    #     return result

