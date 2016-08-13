<?php

namespace App\Bootstraps;

use Illuminate\Http\Request;
use Laravel\Lumen\Application;
use PHPPM\Bootstraps\BootstrapInterface;
use PHPPM\Bootstraps\RequestClassProviderInterface;

final class Lumen implements BootstrapInterface, RequestClassProviderInterface
{
    public function __construct($appEnv, $debug)
    {
        putenv("APP_DEBUG=" . ($debug ? 'true' : 'false'));
        putenv("APP_ENV=" . $appEnv);
    }

    public function getApplication()
    {
        /** @var Application $app */
        $app = require_once __DIR__ . '/../../bootstrap/app.php';

        return $app;
    }

    public function getStaticDirectory()
    {
        return 'public/';
    }

    public function requestClass()
    {
        return Request::class;
    }
}