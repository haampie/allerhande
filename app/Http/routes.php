<?php

$app->get('/', function () use ($app) {
    $starts = ['Steek de', 'Rijg de', 'Snijd de', 'Laat de', 'Neem de', 'Roer de'];
    $start = $starts[array_rand($starts)];
    return response($app['generator']($start, 100));
});
