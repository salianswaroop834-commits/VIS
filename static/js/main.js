/**
 * Nexisure Vehicle Insurance Platform - Interactive Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss Django flash messages after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            try {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                if (bsAlert) {
                    bsAlert.close();
                }
            } catch (e) {
                alert.style.display = 'none';
            }
        }, 6000);
    });

    // Initialize tooltips if Bootstrap is loaded
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    console.info('Nexisure Vehicle Insurance UI initialized successfully.');
});
