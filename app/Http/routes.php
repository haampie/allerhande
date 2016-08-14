<?php

$app->get('/recipe', function () use ($app) {
    $starts = [
        'Steek de',
        'Rijg de',
        'Snijd de',
        'Laat de',
        'Neem de',
        'Roer de',
        'Was de',
        'Verhit de',
        'Breng een',
        'Boen de',
        'Meng de',
    ];
    $start = $starts[array_rand($starts)];
    return response($app['generator']($start, 100));
});
