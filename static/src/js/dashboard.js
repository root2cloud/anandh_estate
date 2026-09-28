/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PropertyDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            data: {
                stats: {},
                charts: { category_data: [], city_data: [], monthly_data: [], price_distribution: [] },
                top_agents: [],
                recent_properties: [],
            },
            loading: true,
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });

        onMounted(() => {
            if (!this.state.loading) {
                this.renderCharts();
            }
        });
    }

    async loadDashboardData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "property.dashboard",
                "get_dashboard_data",
                []
            );
            this.state.data = data;
            this.state.loading = false;

            setTimeout(() => this.renderCharts(), 200);
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.state.loading = false;
        }
    }

    async refreshDashboard() {
        await this.loadDashboardData();
    }

    renderCharts() {
        if (typeof Chart === 'undefined') {
            console.error('Chart.js not loaded');
            return;
        }

        this.renderCategoryChart();
        this.renderCityChart();
    }

    renderCategoryChart() {
        const ctx = document.getElementById('categoryChart');
        if (!ctx) return;

        const data = this.state.data.charts.category_data || [];
        if (data.length === 0) return;

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.map(item => item.name),
                datasets: [{
                    data: data.map(item => item.count),
                    backgroundColor: ['#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6', '#1abc9c'],
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } }
            }
        });
    }

    renderCityChart() {
        const ctx = document.getElementById('cityChart');
        if (!ctx) return;

        const data = this.state.data.charts.city_data || [];
        if (data.length === 0) return;

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.map(item => item.city),
                datasets: [{
                    label: 'Properties',
                    data: data.map(item => item.count),
                    backgroundColor: '#3498db',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } }
            }
        });
    }

    formatNumber(value) {
        if (value >= 10000000) return (value / 10000000).toFixed(2) + ' Cr';
        if (value >= 100000) return (value / 100000).toFixed(2) + ' L';
        return value.toLocaleString('en-IN');
    }

    openPropertyList(domain) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Properties',
            res_model: 'property.property',
            views: [[false, 'list'], [false, 'form']],
            domain: domain || [],
            target: 'current',
        });
    }
}

PropertyDashboard.template = "real_estate_management.PropertyDashboard";
registry.category("actions").add("property_dashboard_action", PropertyDashboard);
