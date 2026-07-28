const chartCanvas = document.getElementById('salesChart');

if (chartCanvas) {
    new Chart(chartCanvas, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [{
                label: 'Продажи',
                data: chartValues,
                borderWidth: 3,
                tension: 0.35,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxTicksLimit: 7,
                        callback: function(value) {
                            const label = this.getLabelForValue(value);

                            if (label.includes('-')) {
                                const p = label.split('-');
                                return p[2] + '.' + p[1];
                            }

                            return label;
                        }
                    }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        maxTicksLimit: 5
                    }
                }
            }
        }
    });
}