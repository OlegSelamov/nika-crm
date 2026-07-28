(function () {
    function drawChart() {
        var canvas = document.getElementById('employeeSalesChart');
        if (!canvas || typeof Chart === 'undefined') return;

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: window.employeeChartLabels,
                datasets: [{
                    data: window.employeeChartValues,
                    borderWidth: 3,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    fill: true,
                    tension: 0.38,
                    borderColor: '#6d5dfc',
                    backgroundColor: 'rgba(109,93,252,.10)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(15,23,42,.06)' },
                        ticks: {
                            callback: function(value) {
                                return Number(value).toLocaleString('ru-RU');
                            }
                        }
                    }
                }
            }
        });
    }

    if (typeof Chart !== 'undefined') {
        drawChart();
    } else {
        var script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
        script.onload = drawChart;
        document.head.appendChild(script);
    }
})();

async function changeProfileTaskStatus(taskId, select) {
    const previous = select.dataset.previous || 'new';
    select.disabled = true;

    try {
        const body = new URLSearchParams({
            status: select.value
        });

        const response = await fetch('/tasks/' + taskId + '/status', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: body.toString()
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Не удалось изменить статус');
        }

        select.dataset.previous = select.value;
        select.className =
            'employee-task-row__status status-' + select.value;

        const card = select.closest('.employee-task-row');

        if (card) {
            card.classList.toggle(
                'is-done',
                select.value === 'done'
            );

            if (
                select.value === 'done' ||
                select.value === 'cancelled'
            ) {
                card.classList.remove('is-overdue');
            }
        }

        window.setTimeout(function () {
            window.location.reload();
        }, 350);

    } catch (error) {
        select.value = previous;
        alert(error.message);
    } finally {
        select.disabled = false;
    }
}