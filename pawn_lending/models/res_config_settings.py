from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pawn_receivable_account_id = fields.Many2one(
        'account.account',
        string='Pawn Loan Receivable Account',
        config_parameter='pawn_management.receivable_account_id',
        domain=[('active', '=', True), ('account_type', '=', 'asset_receivable')],
    )
    pawn_interest_income_account_id = fields.Many2one(
        'account.account',
        string='Interest Income Account',
        config_parameter='pawn_management.interest_income_account_id',
        domain=[('active', '=', True), ('account_type', 'in', ['income', 'income_other'])],
    )
    pawn_penalty_income_account_id = fields.Many2one(
        'account.account',
        string='Penalty Income Account',
        config_parameter='pawn_management.penalty_income_account_id',
        domain=[('active', '=', True), ('account_type', 'in', ['income', 'income_other'])],
    )
    pawn_inventory_account_id = fields.Many2one(
        'account.account',
        string='Inventory Account',
        config_parameter='pawn_management.inventory_account_id',
        domain=[('active', '=', True), ('account_type', 'in', ['asset_current', 'asset_non_current'])],
    )
    pawn_cash_journal_id = fields.Many2one(
        'account.journal',
        string='Default Cash/Bank Journal',
        config_parameter='pawn_management.cash_journal_id',
        domain=[('type', 'in', ['cash', 'bank'])],
    )
